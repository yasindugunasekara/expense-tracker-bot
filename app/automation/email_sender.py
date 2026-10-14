
import base64
import os
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

TOKEN_FILE = PROJECT_ROOT / "token.json"


def send_email(
    subject: str,
    body: str,
    to_email: str | None = None,
    html_body: str | None = None,
) -> dict:
    recipient = to_email or os.getenv("GMAIL_REPORT_TO")

    if not recipient:
        raise ValueError("Set GMAIL_REPORT_TO in your .env file.")

    if not TOKEN_FILE.exists():
        raise FileNotFoundError(f"Gmail token not found: {TOKEN_FILE}")

    credentials = Credentials.from_authorized_user_file(
        str(TOKEN_FILE)
    )

    if not credentials.has_scopes(
        ["https://www.googleapis.com/auth/gmail.send"]
    ):
        raise PermissionError(
            "Gmail sending permission is missing. "
            "Reauthorize Gmail with the gmail.send scope."
        )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    if not credentials.valid:
        raise PermissionError(
            "Gmail credentials are invalid. Reauthorize Gmail."
        )

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

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    result = (
        service.users()
        .messages()
        .send(
            userId="me",
            body={"raw": encoded_message},
        )
        .execute()
    )

    return {
        "success": True,
        "message_id": result.get("id"),
        "recipient": recipient,
    }
