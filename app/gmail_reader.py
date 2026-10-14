
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_gmail_service():
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Missing credentials file: {CREDENTIALS_FILE}"
        )

    credentials = None

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if not credentials or not credentials.valid:
        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            print("\n🔑 Opening your browser to authorize Gmail access...")
            print("👉 If your browser does not open automatically, copy and paste the URL shown below into your browser.")
            print("👉 Log into your Google account and click 'Allow'.\n")
            credentials = flow.run_local_server(
                    host="localhost",
                    port=0,
                    open_browser=True,
                    timeout_seconds=600,
                    success_message=(
                        "Gmail authorization successful! "
                        "You can close this browser tab."
                    ),
            )

        TOKEN_FILE.write_text(
            credentials.to_json(), encoding="utf-8"
        )

    return build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


def find_receipt_emails(max_results=10):
    service = get_gmail_service()

    query = (
        'newer_than:30d '
        '{PickMe HelaPay}'
    )

    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=max_results,
        )
        .execute()
    )

    messages = response.get("messages", [])

    print(f"Matching Gmail messages found: {len(messages)}")

    for message in messages:
        details = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )

        headers = details.get("payload", {}).get("headers", [])
        header_map = {
            item["name"].lower(): item["value"]
            for item in headers
        }

        print("-" * 50)
        print("Message ID:", message["id"])
        print("From:", header_map.get("from", "Unknown"))
        print("Subject:", header_map.get("subject", ""))
        print("Date:", header_map.get("date", ""))
        print("Snippet:", details.get("snippet", ""))


if __name__ == "__main__":
    find_receipt_emails()
