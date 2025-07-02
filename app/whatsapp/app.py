# Standard library imports
import os, logging
from datetime import datetime

# Third-party library imports
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Local application imports
from chat.clients.twilio import TwilioWhatsAppClient, TwilioWhatsAppMessage
from chat.handlers.openai import (
    chat_completion as chatgpt_completion,
    voice_transcription as whisper_transcription,
)
from app.handlers import (
    check_and_send_image_generation,
    ensure_user_language,
    verify_image_generation,
    verify_and_process_media,
    check_conversation_end,
)
from app.whatsapp.chat import Sender, OpenAIChatManager

# Commented out import for image captioning
# from chat.handlers.image import image_captioning

# Load environment variables from a .env file
load_dotenv()

# Configure logging for the application
logging.basicConfig()
logger = logging.getLogger("WP-APP")
logger.setLevel(logging.DEBUG)

# --- Chat Agent Configuration ---

# Load the chat start template from a file or use a default
start_template = os.environ.get("CHAT_START_TEMPLATE")
if start_template and os.path.exists(start_template):
    with open(start_template, "r") as f:
        start_template = f.read()

# Set up options for the chat agent's behavior
chat_options = dict(
    model=os.environ.get("CHAT_MODEL", "gpt-3.5-turbo"),
    agent_name=os.environ.get("AGENT_NAME"),
    start_system_message=start_template,
    goodbye_message="Goodbye! I'll be here if you need me.",
    voice_transcription=True,
    allow_images=True,
)

# Set up options for the underlying language model
model_options = dict(
    model=os.environ.get("CHAT_MODEL", "gpt-3.5-turbo"),
    max_tokens=int(os.environ.get("MAX_TOKENS", 1000)),
    temperature=float(os.environ.get("TEMPERATURE", 1.2)),
    top_p=int(os.environ.get("TOP_P", 1)),
    frequency_penalty=float(os.environ.get("FREQUENCY_PENALTY", 0.3)),
    presence_penalty=float(os.environ.get("PRESENCE_PENALTY", 0.1)),
    n=1,
)

# --- Client and App Initialization ---

# Create the Twilio WhatsApp client for sending and receiving messages
chat_client = TwilioWhatsAppClient(
    account_sid=os.environ.get("TWILIO_ACCOUNT_SID"),
    auth_token=os.environ.get("TWILIO_AUTH_TOKEN"),
    from_number=os.environ.get("TWILIO_WHATSAPP_NUMBER", "+14155238886"),
)

# Initialize the Flask application
app = Flask(__name__)


# --- Webhook for Incoming WhatsApp Messages ---

@app.route("/whatsapp/reply", methods=["POST"])
async def reply_to_whatsapp_message():
    """
    Handles incoming WhatsApp messages, processes them, and sends a reply.
    """
    logger.info(f"Obtained request: {dict(request.values)}")

    # --- Chat Session Management ---

    # Identify the sender and get or create a chat session
    sender = Sender(
        phone_number=request.values.get("From"),
        name=request.values.get("ProfileName", request.values.get("From")),
    )
    chat = OpenAIChatManager.get_or_create(sender, logger=logger, **chat_options)

    # Set up the initial system message with user-specific details
    chat.start_system_message = chat_options.get("start_system_message").format(
        user=sender.name, today=datetime.now().strftime("%Y-%m-%d")
    )
    chat.messages[0] = chat.make_message(chat.start_system_message, role="system")

    # --- Message Processing ---

    # Parse the incoming message and process any media attachments
    new_message = chat_client.parse_request_values(request.values)
    msg = verify_and_process_media(new_message, chat)
    
    # Check if the message is empty or a goodbye message
    if message_empty_or_goodbye(msg, chat):
        return jsonify({"status": "ok"})
    
    # If this is the first message, ensure the user's language is set
    logger.info("Chat has %d messages", len(chat.messages))
    if len(chat.messages) == 1:
        await ensure_user_language(chat, text=msg)
    
    # --- Reply Generation and Sending ---

    # Add the user's message to the chat and generate a reply
    chat.add_message(msg, role="user")
    reply = chatgpt_completion(chat.messages, **model_options).strip()
    logger.info(f"Generated reply of length {len(reply)}")
    
    # Check if the reply is requesting an image generation
    reply, img_prompt = verify_image_generation(reply)
    
    # Send the generated reply to the user
    chat_client.send_message(
        reply,
        chat.sender.phone_number,
        on_failure="Sorry, I didn't understand that. Please try again.",
    )
    
    # Add the assistant's reply to the chat history
    chat.add_message(reply, role="assistant")

    # If an image was requested, generate and send it
    if img_prompt:
        chat.add_message(f'[img:"{img_prompt}"]', role="system")
        await check_and_send_image_generation(img_prompt, chat, client=chat_client)
    
    # --- Finalization ---

    # Save the updated chat session
    chat.save()
    logger.info(
        f"--------------\nConversation:\n{chat.get_conversation()}\n----------------"
    )
    return jsonify({"status": "ok"})


# --- Helper Functions ---

def message_empty_or_goodbye(msg, chat):
    """
    Checks if the message is empty or if it signals the end of the conversation.
    """
    if check_message_empty(msg, chat):
        reply = "Sorry, I didn't understand that. Please try again."
        chat_client.send_message(reply, chat.sender.phone_number)
        return True
    if check_conversation_end(msg, chat):
        chat_client.send_message(
            chat.goodbye_message.format(user=chat.sender.name),
            chat.sender.phone_number,
        )
        return True
    return False

def check_message_empty(msg, chat):
    """
    Checks if the message is None or consists only of whitespace.
    """
    if msg is None or msg.strip() == "":
        # If the message is empty, send a default response
        return True
    return False


# --- Webhook for WhatsApp Status Updates ---

@app.route("/whatsapp/status", methods=["POST"])
def process_whatsapp_status():
    """
    Handles status updates from WhatsApp (e.g., message delivery status).
    """
    logger.info(f"Obtained request: {dict(request.values)}")
    return jsonify({"status": "ok"})
