"""
Google Sheets integration — logs confirmed bookings to a shared spreadsheet.

The spreadsheet is auto-created on first use and shared with the configured
SHEETS_SHARE_EMAIL (default: bhtest270326@gmail.com).
Spreadsheet ID is persisted in app_state so it survives restarts.
"""
import os
import logging
import concurrent.futures
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _with_timeout(fn, timeout=8):
    """Run a zero-argument callable in a thread pool, raising TimeoutError after *timeout* seconds."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error('Google Sheets API call timed out after %ds', timeout)
            raise TimeoutError('Sheets API timeout')

SHEETS_SHARE_EMAIL = os.environ.get('SHEETS_SHARE_EMAIL', os.environ.get('OWNER_EMAIL', ''))
SPREADSHEET_TITLE = 'Wheel Doctor Bookings'
SPREADSHEET_ID_KEY = 'google_sheets_spreadsheet_id'

SHEET_HEADERS = [
    'Booking ID', 'Date Created', 'Status',
    'Customer Name', 'Phone', 'Email',
    'Vehicle Make', 'Vehicle Model', 'Vehicle Year', 'Vehicle Colour',
    'Service Type', 'Num Rims', 'Damage Description',
    'Address', 'Suburb', 'Preferred Date', 'Preferred Time',
    'Notes', 'Confirmed At'
]


def _get_or_create_spreadsheet(sheets_svc, drive_svc, state) -> str:
    """Return spreadsheet ID — create and share if it doesn't exist yet."""
    existing_id = state.get_app_state(SPREADSHEET_ID_KEY)
    if existing_id:
        return existing_id

    # Create new spreadsheet
    _create_req = sheets_svc.spreadsheets().create(body={
        'properties': {'title': SPREADSHEET_TITLE},
        'sheets': [{'properties': {'title': 'Bookings'}}]
    })
    spreadsheet = _with_timeout(_create_req.execute)

    spreadsheet_id = spreadsheet['spreadsheetId']
    logger.info(f"Created Google Sheet: {spreadsheet_id}")

    # Write headers
    _headers_req = sheets_svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range='Bookings!A1',
        valueInputOption='RAW',
        body={'values': [SHEET_HEADERS]}
    )
    _with_timeout(_headers_req.execute)

    # Bold the header row and freeze it
    try:
        _fmt_req = sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [
                {'repeatCell': {
                    'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1},
                    'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
                    'fields': 'userEnteredFormat.textFormat.bold'
                }},
                {'updateSheetProperties': {
                    'properties': {'sheetId': 0, 'gridProperties': {'frozenRowCount': 1}},
                    'fields': 'gridProperties.frozenRowCount'
                }}
            ]}
        )
        _with_timeout(_fmt_req.execute)
    except Exception as e:
        logger.warning(f"Could not format header row: {e}")

    # Share with configured email
    try:
        _share_req = drive_svc.permissions().create(
            fileId=spreadsheet_id,
            body={'type': 'user', 'role': 'writer', 'emailAddress': SHEETS_SHARE_EMAIL},
            sendNotificationEmail=True,
            emailMessage=f"Your Wheel Doctor booking log spreadsheet is ready."
        )
        _with_timeout(_share_req.execute)
        logger.info(f"Shared spreadsheet with {SHEETS_SHARE_EMAIL}")
    except Exception as e:
        logger.warning(f"Could not share spreadsheet with {SHEETS_SHARE_EMAIL}: {e}")

    # Persist the ID
    state.set_app_state(SPREADSHEET_ID_KEY, spreadsheet_id)
    return spreadsheet_id


def append_booking_row(booking_id: str, booking: dict):
    """
    Append a row to the Wheel Doctor Bookings sheet for a confirmed booking.

    Args:
        booking_id: The booking ID string (e.g. 'A1B2C3D4')
        booking:    Full booking dict from StateManager (includes booking_data, customer_email, etc.)
    """
    try:
        from google_auth import get_sheets_service, SHEETS_SCOPES
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from state_manager import StateManager

        sheets_svc = get_sheets_service()

        # Build Drive service using Sheets scopes (not Gmail/Calendar scopes)
        try:
            creds = Credentials(
                token=None,
                refresh_token=os.environ['GOOGLE_SHEETS_REFRESH_TOKEN'],
                client_id=os.environ['GOOGLE_CLIENT_ID'],
                client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
                token_uri='https://oauth2.googleapis.com/token',
                scopes=SHEETS_SCOPES
            )
            drive_svc = build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.warning(f"Could not build Drive service for sheet sharing: {e}")
            drive_svc = None

        state = StateManager()

        # If drive_svc failed, we can still try sheets without sharing
        class _FakeDrive:
            def permissions(self): return self
            def create(self, **kw): return self
            def execute(self): pass

        if drive_svc is None:
            logger.warning("Using FakeDrive stub — spreadsheet will not be shared with owner")
        spreadsheet_id = _get_or_create_spreadsheet(sheets_svc, drive_svc or _FakeDrive(), state)

        bd = booking.get('booking_data', {})

        row = [
            booking_id,
            booking.get('created_at', ''),
            booking.get('status', 'confirmed'),
            bd.get('customer_name', ''),
            bd.get('customer_phone', ''),
            booking.get('customer_email') or bd.get('customer_email', ''),
            bd.get('vehicle_make', ''),
            bd.get('vehicle_model', ''),
            bd.get('vehicle_year', ''),
            bd.get('vehicle_colour', ''),
            bd.get('service_type', ''),
            str(bd.get('num_rims', '')),
            bd.get('damage_description', ''),
            bd.get('address', ''),
            bd.get('suburb', ''),
            bd.get('preferred_date', ''),
            bd.get('preferred_time', ''),
            bd.get('notes', ''),
            booking.get('confirmed_at', datetime.now(timezone.utc).isoformat()),
        ]

        _append_req = sheets_svc.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range='Bookings!A1',
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body={'values': [row]}
        )
        _with_timeout(_append_req.execute)

        logger.info(f"Booking {booking_id} appended to Google Sheet {spreadsheet_id}")

    except Exception as e:
        logger.error(f"Google Sheets append error for booking {booking_id}: {e}", exc_info=True)
