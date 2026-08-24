import os
from typing import Any
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()


def get_twilio_client() -> Client:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    if not account_sid or not auth_token:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured in .env")

    return Client(account_sid, auth_token)


def send_whatsapp_message(
    to_phone: str,
    message_text: str,
    media_url: str | None = None,
) -> dict:
    """
    Send a WhatsApp message via Twilio.
    to_phone: e.g. "+919996570779"
    """
    client = get_twilio_client()
    from_wa = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
    
    # Format recipient
    clean_to = to_phone.strip().replace(" ", "").replace("-", "")
    if not clean_to.startswith("whatsapp:"):
        clean_to = f"whatsapp:{clean_to}"

    kwargs: dict[str, Any] = {
        "from_": from_wa,
        "to": clean_to,
        "body": message_text,
    }
    if media_url:
        kwargs["media_url"] = [media_url]

    message = client.messages.create(**kwargs)

    return {
        "sid": message.sid,
        "status": str(message.status),
        "to": clean_to,
    }


def send_tenant_greeting(
    tenant_name: str,
    tenant_phone: str,
    onboarding_id: str | int,
    property_name: str | None = None,
) -> dict:
    """
    Send automated greeting and document request message to newly onboarded tenant.
    """
    flat = property_name or "your assigned unit"
    text = (
        f"👋 *Hello {tenant_name}! Welcome to {flat}.*\n\n"
        f"Your onboarding has been initiated *(ID: ONB-{onboarding_id})*.\n\n"
        f"To complete your verification and generate your *Rent Agreement*, "
        f"please reply directly to this message with clear photos/PDF of:\n"
        f"1. 📄 *Aadhaar Card* (Front & Back)\n"
        f"2. 📄 *PAN Card*\n\n"
        f"⚡ _Our AI verification engine will process your documents automatically!_"
    )

    return send_whatsapp_message(to_phone=tenant_phone, message_text=text)


def send_verification_update(
    tenant_phone: str,
    doc_type: str,
    status: str,
    details: str | None = None,
) -> dict:
    """
    Notify tenant about document verification result.
    """
    if status.upper() == "APPROVED":
        text = f"✅ *{doc_type} Verified Successfully!*\n{details or ''}"
    else:
        text = (
            f"⚠️ *{doc_type} Verification Issue*\n"
            f"{details or 'The photo was unclear. Please resend a clearer image.'}"
        )

    return send_whatsapp_message(to_phone=tenant_phone, message_text=text)
