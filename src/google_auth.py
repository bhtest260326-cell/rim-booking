import os
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar',
]

# Sheets/Drive scopes are kept separate — they require a distinct refresh token
# issued with these scopes. Set GOOGLE_SHEETS_REFRESH_TOKEN env var once
# re-authorized, and google_sheets.py will use it independently.
SHEETS_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]

def _require_env(name: str) -> str:
    """Return the value of an environment variable or raise with a helpful message."""
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} environment variable is not set")
    return value


def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=_require_env('GOOGLE_REFRESH_TOKEN'),
        client_id=_require_env('GOOGLE_CLIENT_ID'),
        client_secret=_require_env('GOOGLE_CLIENT_SECRET'),
        token_uri='https://oauth2.googleapis.com/token',
        scopes=SCOPES
    )
    return build('gmail', 'v1', credentials=creds)

def get_calendar_service():
    creds = Credentials(
        token=None,
        refresh_token=_require_env('GOOGLE_REFRESH_TOKEN'),
        client_id=_require_env('GOOGLE_CLIENT_ID'),
        client_secret=_require_env('GOOGLE_CLIENT_SECRET'),
        token_uri='https://oauth2.googleapis.com/token',
        scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=creds)

def get_sheets_service():
    """Return an authenticated Google Sheets API service.

    Requires GOOGLE_SHEETS_REFRESH_TOKEN env var — a refresh token issued with
    spreadsheets + drive.file scopes (separate from the main Gmail/Calendar token).
    Raises KeyError if the env var is not set.
    """
    sheets_token = _require_env('GOOGLE_SHEETS_REFRESH_TOKEN')
    creds = Credentials(
        token=None,
        refresh_token=sheets_token,
        client_id=_require_env('GOOGLE_CLIENT_ID'),
        client_secret=_require_env('GOOGLE_CLIENT_SECRET'),
        token_uri='https://oauth2.googleapis.com/token',
        scopes=SHEETS_SCOPES,
    )
    return build('sheets', 'v4', credentials=creds)
