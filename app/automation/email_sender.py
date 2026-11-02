
import base64
import os
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")



def send_email(
    subject: str,
    body: str,
    to_email: str | None = None,
    html_body: str | None = None,
) -> dict:
    recipient = to_email or os.getenv("GMAIL_REPORT_TO")

    if not recipient:
        raise ValueError("Set GMAIL_REPORT_TO in your .env file.")

    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = subject

    # Plain-text fallback for email clients that cannot display HTML.
    message.set_content(body)

    # Modern HTML email for Gmail and other email clients.
    if html_body:
        message.add_alternative(
            html_body,
            subtype="html",
        )

    encoded_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    from app.gmail_auth import get_gmail_service
    service = get_gmail_service(["https://www.googleapis.com/auth/gmail.send"])

    result = (
        service.users()
        .messages()
        .send(
            userId="me",
            body={"raw": encoded_message},
        )
        .execute()
    )

    if not result.get("id"):
        raise RuntimeError("Gmail did not confirm a message ID.")
    return {
        "success": True,
        "message_id": result.get("id"),
        "recipient": recipient,
    }
