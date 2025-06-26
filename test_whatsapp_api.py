import requests

# Change this URL if testing from another machine or using ngrok
API_URL = "http://127.0.0.1:5001/whatsapp/reply"

# Example payload simulating a WhatsApp webhook POST
payload = {
    "From": "+1234567890",
    "ProfileName": "Test User",
    "Body": "Hello, WhatsApp bot!"
}

response = requests.post(API_URL, data=payload)

print("Status code:", response.status_code)
print("Response:", response.text)