"""Shared headless Gmail authorization; interactive consent is an explicit command."""
import httplib2
from google_auth_httplib2 import AuthorizedHttp
import os
import tempfile
from pathlib import Path
from filelock import FileLock
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = Path(os.getenv("GMAIL_TOKEN_FILE", str(ROOT / "gmail-state" / "token.json")))
LEGACY_TOKEN = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]


def token_path():
    if TOKEN_FILE.exists() or not LEGACY_TOKEN.exists():
        return TOKEN_FILE
    return LEGACY_TOKEN


def save_token(path, credentials):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".gmail-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(credentials.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def get_credentials(required_scopes):
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=60):
        try:
            # Read stored grants, never pretend requested scopes were already granted.
            credentials = Credentials.from_authorized_user_file(str(path))
        except (OSError, ValueError, KeyError) as exc:
            raise PermissionError("Gmail token missing or malformed. Run python -m app.gmail_auth locally.") from None
        if not credentials.has_scopes(required_scopes):
            raise PermissionError("Gmail permissions missing. Run python -m app.gmail_auth locally and grant read/send access.")
        if not credentials.valid:
            if not credentials.refresh_token:
                raise PermissionError("Gmail refresh token missing. Run python -m app.gmail_auth locally.")
            try:
                credentials.refresh(Request())
            except RefreshError:
                raise PermissionError("Gmail grant expired or revoked. Run python -m app.gmail_auth locally.") from None
            except TransportError:
                raise ConnectionError("Gmail token refresh temporarily unavailable.") from None
            if not credentials.valid:
                raise PermissionError("Gmail refresh returned invalid credentials; reauthorize locally.")
            save_token(path, credentials)
        return credentials


def get_gmail_service(required_scopes=None):
    credentials = get_credentials(required_scopes or SCOPES)
    http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=30))
    return build("gmail", "v1", http=http, cache_discovery=False)


def authorize():
    from google_auth_oauthlib.flow import InstalledAppFlow
    path = TOKEN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(ROOT / "credentials.json"), SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True, timeout_seconds=600, access_type="offline", prompt="consent")
    with FileLock(str(path) + ".lock", timeout=60):
        save_token(path, credentials)
    print("Gmail authorization saved. Transfer gmail-state/token.json securely to Azure.")


if __name__ == "__main__":
    authorize()
