"""
Handlers for OpenAI's Completion and Chat Completion APIs
"""
import logging, re
from typing import List

import openai
from dotenv import load_dotenv
import os
load_dotenv()
openai_api_key = os.environ.get("OPENAI_API_KEY")
openai_base_url = os.environ.get("OPENAI_BASE_URL")
try:
    client = openai.OpenAI(api_key=openai_api_key, base_url=openai_base_url)
except AttributeError:
    client = None
from chat.clients import ChatClient

__all__ = [
    "text_completion",
    "chat_completion",
    "code_generation",
    "whisper_voice_transcription",
    "dalle_text_to_image",
]

def text_completion(
    prompt: str,
    chat: ChatClient = None,
    engine: str = "text-davinci-003",
    **kwargs
):
    """
    Generates text completion using OpenAI's Completion API.

    Parameters
    ----------
    prompt : str
        The prompt to complete.
    chat : ChatClient, optional
        The chat client, by default None
    engine : str, optional
        The engine to use, by default "text-davinci-003"
    **kwargs
        Additional keyword arguments to pass to the Completion API.
        See https://platform.openai.com/docs/api-reference/completions for a list of
        valid parameters.
    """
    if "model" in kwargs:
        engine = kwargs.pop("model")
    logging.info(f"Querying OpenAI's Completion API with prompt '{prompt}'")
    if engine == 'gpt-3.5-turbo':
        return chat_completion(prompt, model=engine, **kwargs)
    elif isinstance(prompt, list):
        prompt = "\n".join(f"{d['role'].upper()}: {d['content']}" for d in prompt)
    response = openai.Completion.create(
        prompt=prompt,
        engine=engine,
        **kwargs
    )
    return response.get("choices",[{}])[0].get("text")

def chat_completion(
    messages: List[dict],
    model: str = "gpt-3.5-turbo",
    **kwargs
):
    """
    Generates chat completion using OpenAI's Chat Completion API.

    Parameters
    ----------
    messages : List[dict]
        A list of messages to complete.
    chat : ChatClient, optional
        The chat client, by default None
    model : str, optional
        The model to use, by default "gpt-3.5-turbo"
    **kwargs
        Additional keyword arguments to pass to the Chat Completion API.
        See https://platform.openai.com/docs/api-reference/chat/create for a list of
        valid parameters.
    """
    if "engine" in kwargs:
        model = kwargs.pop("engine")
    if client:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
    else:
        raise RuntimeError(
            "OpenAI client is not available or your openai-python package is outdated. "
            "Please upgrade to the latest openai package and ensure your API key and base URL are correct."
        )

    # For OpenAI v1 client, response is a pydantic object, not a dict
    if hasattr(response, "choices"):
        # v1 client: response.choices is a list of objects with .message.content
        return response.choices[0].message.content
    # Legacy: dict-like
    return response.get("choices",[{}])[0].get("message", {}).get("content")


def text_translation(
    text: str,
    to: str = "english",
    from_: str = None,
    engine: str = "text-da-vinci-003",
    prompt: str = None,
    examples: List[str] = None,
    **kwargs
):
    """
    Translates text using OpenAI's Completion API.
    It injects a translation prompt into the text to be translated

    Parameters
    ----------
    text : str
        The text to translate.
    to : str, optional
        The language to translate to. By default "english".
    from_ : str, optional
        The language to translate from. By default the language is inferred from the
        text.
    engine : str, optional
        The engine to use, by default "text-davinci-003" for chat completion.
    prompt : str, optional
        The prompt to inject into the text to be translated.
    examples : List[Tuple], optional
        A list of few-show examples to use for the translation task in the form of
        (text, translation) tuples. e.g. [("Hello world", "Bonjour le monde")] for
        English to French translation.
    **kwargs
        Additional keyword arguments to pass to the Completion API.
    
    Returns
    -------
    str
        The translated text.
    
    Usage
    -----
    >>> translate_text("Hello world", to="french")
    "Bonjour le monde"
    >>> translate_text("Comment allez-vous?", from_="french", to="spanish", examples=[""Bonjour le monde", "Hola Mundo"])
    "¿Cómo estás?"
    """
    logging.info(f"Querying OpenAI's Completion API with prompt '{prompt}'")
    if prompt is None:
        if from_ is None:
            prompt = f"Translate the text '{text}' to {to.capitalize()}."
        else:
            prompt = f"Translate the text '{text}' from {from_.capitalize()} to {to.capitalize()}."
    if examples is not None:
        prompt += " For example: " + ", ".join(
            [f"{txt} -> {translation}" for txt, translation in examples]
        )
    prompt += f"\n----\n{text} ->"
    if engine == 'gpt-3.5-turbo':
        messages = [
            {'role': 'user', 'content': prompt},
        ]
        # print(f"Querying OpenAI's Chat Completion API with messages {messages}")
        result_text = chat_completion(messages, model=engine, **kwargs)
    else:
        # print(f"Querying OpenAI's Completion API with prompt '{prompt}'")
        kwargs['stop'] = '\n'
        result_text = text_completion(prompt, engine=engine, **kwargs)
    return re.sub(r" ->.*", "", result_text).strip()

async def atext_translation(*args, **kwargs):
    return text_translation(*args, **kwargs)

def language_detection(
    text: str,
    engine: str = "gpt-3.5-turbo",
    prompt: str = None,
    examples: List[str] = None,
    **kwargs
) -> str:
    """ 
    Recognizes the language of a text using OpenAI's Completion API.
    It injects a language recognition prompt into the text to be recognized

    Parameters
    ----------
    text : str
        The text to recognize.
    engine : str, optional
        The engine to use, by default "gpt-3.5-turbo" for chat completion.
    prompt : str, optional
        The prompt to inject into the text to be recognized.
    examples : List[Tuple], optional
        A list of few-show examples to use for the language recognition task in the
        form of (text, language) tuples. e.g. [("Hello world", "english")]
    **kwargs
        Additional keyword arguments to pass to the Completion API.
    """
    if prompt is None:
        prompt = f"You are a language recognition program. You can only output a single word saying the language of a given text."
    else:
        prompt = prompt.format(text=text)
    if examples is None:
        examples = [
            ("Hello world", "english"),
            ("Bonjour le monde", "french"),
            ("Hola mundo", "spanish"),
            ("Hallo Welt", "german"),
        ]
    prompt += " Some \"text\" -> reply example outputs are: " + ", ".join(
        [f"\"{txt}\" -> {language}" for txt, language in examples]
    )
    prompt += f"\n---\n{text} ->"
    if engine == 'gpt-3.5-turbo':
        messages = [
            {'role': 'system', 'content': prompt},
        ]
        # kwargs['stop'] = ['\n']
        print(f"Querying OpenAI's Chat Completion API with messages {messages}")
        result_text = chat_completion(messages, model=engine, **kwargs)
    else:
        # print(f"Querying OpenAI's Completion API with prompt '{prompt}'")
        kwargs['stop'] = '\n'
        result_text = text_completion(prompt, engine=engine, **kwargs)
    detected_lang = re.sub(r" ->.*", "", result_text).strip().lower()
    if len(detected_lang.split()) > 1:
        detected_lang = detected_lang.split()[0]
    return detected_lang

async def alanguage_detection(*args, **kwargs):
    return language_detection(*args, **kwargs)

def code_generation(
    prompt: str,
    chat: ChatClient = None,
    engine: str = "davinci-codex",
    **kwargs
):
    """
    Generates code completion using OpenAI's Completion API.
    """
    logging.info(f"Querying OpenAI's Completion API with prompt '{prompt}'")
    response = openai.Completion.create(
        prompt=prompt,
        engine=engine,
        **kwargs
    )
    return response.get("choices",[{}])[0].get("text")