import os
import requests
from fastmcp import FastMCP
from dotenv import load_dotenv
load_dotenv()

mcp = FastMCP("whatsapp-mcp")


WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")


def _require_env():
    if not WHATSAPP_TOKEN and WHATSAPP_PHONE_ID:
        raise RuntimeError("please set whatsapp token and phone number id in the environment variables")
    
@mcp.tool
def send_message(phone_number: int, message: str) -> dict:
    """Send a WhatsApp message to a phone number."""
    _require_env()
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
    }
    payload = { "messaging_product": "whatsapp", "to": phone_number, "type": "text", "text": {"body": message}, }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        print("Message sent successfully")
        return {"status": "success", "message": "Message sent successfully", "data": response.json()}
    else:
        print(f"Failed to send message")
        return {"status": "error", "message": f"Failed to send message: {response.status_code} - {response.text}"}


if __name__ == "__main__":
    #print("Whatsapp token", WHATSAPP_TOKEN, "phone id", WHATSAPP_PHONE_ID)
    mcp.run(transport="http", host="127.0.0.1", port=8000)