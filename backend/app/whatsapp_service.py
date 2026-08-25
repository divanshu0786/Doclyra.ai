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
    property_address: str | None = None,
) -> dict:
    """
    Send automated greeting and document request message to newly onboarded tenant.
    Requests: Aadhaar, PAN, Passport size photo, and Rent Agreement.
    """
    prop = property_name or "your assigned property"
    addr_text = f" ({property_address})" if property_address else ""

    text = (
        f"👋 *Welcome {tenant_name}!* 🏡\n\n"
        f"Your onboarding has been initiated for *{prop}*{addr_text} *(ID: ONB-{onboarding_id})*.\n\n"
        f"To complete your verification, please send clear photos/PDFs of the following 4 documents:\n"
        f"1. 📄 *Aadhaar Card* (Front & Back)\n"
        f"2. 📄 *PAN Card*\n"
        f"3. 📸 *Passport Size Photo* (Clear headshot)\n"
        f"4. 📝 *Rent Agreement*\n\n"
        f"⚡ _Our automated AI system will verify them immediately and keep you updated here!_"
    )

    return send_whatsapp_message(to_phone=tenant_phone, message_text=text)


def send_approval_notification(
    tenant_phone: str,
    doc_type: str,
    tenant_name: str | None = None,
) -> dict:
    """
    Notify tenant on WhatsApp that a document has been APPROVED.
    """
    greeting = f"Hi {tenant_name}! " if tenant_name else ""
    text = (
        f"✅ *{greeting}Your {doc_type} has been Verified & Approved!*\n\n"
        f"All details (Name, DOB, format) matched successfully. 🎉"
    )
    return send_whatsapp_message(to_phone=tenant_phone, message_text=text)


def send_rejection_notification(
    tenant_phone: str,
    doc_type: str,
    layman_reason: str,
    tenant_name: str | None = None,
) -> dict:
    """
    Notify tenant on WhatsApp that a document was REJECTED with a clear reason.
    """
    greeting = f"Hi {tenant_name}, " if tenant_name else ""
    text = (
        f"⚠️ *{greeting}Issue with your {doc_type}*\n\n"
        f"We could not approve this document due to:\n"
        f"👉 *{layman_reason}*\n\n"
        f"Please re-upload a clear, correct document to proceed. 🙏"
    )
    return send_whatsapp_message(to_phone=tenant_phone, message_text=text)
