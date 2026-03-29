"""
backup_handler.py
=================
Automated SQLite database backup to Google Drive.
Keeps the last N backups (default 7) and rotates old ones.
Uses the Sheets/Drive refresh token (GOOGLE_SHEETS_REFRESH_TOKEN)
which already has drive.file scope.
"""

import os
import sqlite3
import tempfile
import logging
from datetime import datetime, timezone, timedelta

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from state_manager import StateManager, DB_PATH

logger = logging.getLogger(__name__)

# Perth timezone offset (AWST = UTC+8)
_PERTH_TZ = timezone(timedelta(hours=8))

# Module-level cached Drive service
_drive_service = None


def _get_drive_service():
    """Build a Google Drive v3 service using the Sheets/Drive refresh token.

    Caches the service in a module-level variable.  Returns None if
    credentials are missing (logs a warning, does not crash).
    """
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    try:
        refresh_token = os.environ.get('GOOGLE_SHEETS_REFRESH_TOKEN')
        client_id = os.environ.get('GOOGLE_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

        if not all([refresh_token, client_id, client_secret]):
            logger.warning(
                "_get_drive_service: missing one or more env vars "
                "(GOOGLE_SHEETS_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)"
            )
            return None

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri='https://oauth2.googleapis.com/token',
            scopes=['https://www.googleapis.com/auth/drive.file'],
        )
        _drive_service = build('drive', 'v3', credentials=creds)
        return _drive_service
    except Exception as e:
        logger.warning("_get_drive_service: failed to build Drive service: %s", e)
        return None


def _get_or_create_backup_folder(drive_svc):
    """Return the Drive folder ID for backups, creating it if necessary.

    Stores the folder ID in app_state under key ``drive_backup_folder_id``
    so subsequent calls avoid re-creating the folder.
    """
    state = StateManager()

    folder_id = state.get_app_state('drive_backup_folder_id')

    # Verify the folder still exists in Drive
    if folder_id:
        try:
            meta = drive_svc.files().get(
                fileId=folder_id, fields='id, trashed'
            ).execute()
            if not meta.get('trashed', False):
                return folder_id
            logger.info(
                "_get_or_create_backup_folder: folder %s was trashed, creating new one",
                folder_id,
            )
        except Exception:
            logger.info(
                "_get_or_create_backup_folder: folder %s not found, creating new one",
                folder_id,
            )

    # Create a new folder
    file_metadata = {
        'name': 'RimBooking-Backups',
        'mimeType': 'application/vnd.google-apps.folder',
    }
    folder = drive_svc.files().create(
        body=file_metadata, fields='id'
    ).execute()
    folder_id = folder['id']

    state.set_app_state('drive_backup_folder_id', folder_id)
    logger.info("Created Drive backup folder: %s", folder_id)
    return folder_id


def _get_row_counts():
    """Return a summary string with row counts for key tables."""
    try:
        conn = sqlite3.connect(DB_PATH)
        tables = ['bookings', 'clarifications', 'app_state']
        parts = []
        for table in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                parts.append(f"{table}: {row[0]}")
            except sqlite3.OperationalError:
                pass
        conn.close()
        return ", ".join(parts) if parts else "no tables"
    except Exception as e:
        return f"error reading counts: {e}"


def backup_database_to_drive(max_backups: int = 7) -> dict:
    """Create a backup of the SQLite database and upload it to Google Drive.

    Uses the sqlite3 backup API for a safe online copy, uploads to a
    dedicated ``RimBooking-Backups`` folder, and rotates old backups so
    that at most *max_backups* are retained.

    Returns a dict describing the outcome.
    """
    try:
        drive_svc = _get_drive_service()
        if drive_svc is None:
            return {"ok": False, "error": "Drive not configured"}

        folder_id = _get_or_create_backup_folder(drive_svc)

        # ----- Safe copy via sqlite3 backup API -----
        now = datetime.now(_PERTH_TZ)
        backup_name = now.strftime("booking_backup_%Y-%m-%d_%H%M%S.db")

        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.db')
        os.close(tmp_fd)

        try:
            source = sqlite3.connect(DB_PATH)
            dest = sqlite3.connect(tmp_path)
            source.backup(dest)
            dest.close()
            source.close()
        except Exception as e:
            logger.error("backup_database_to_drive: sqlite3 backup failed: %s", e)
            os.unlink(tmp_path)
            return {"ok": False, "error": f"sqlite3 backup failed: {e}"}

        file_size = os.path.getsize(tmp_path)
        row_counts = _get_row_counts()

        # ----- Upload to Drive -----
        file_metadata = {
            'name': backup_name,
            'parents': [folder_id],
            'description': (
                f"Size: {file_size:,} bytes | Rows: {row_counts} | "
                f"Created: {now.strftime('%Y-%m-%d %H:%M:%S AWST')}"
            ),
        }
        media = MediaFileUpload(tmp_path, mimetype='application/x-sqlite3')
        uploaded = drive_svc.files().create(
            body=file_metadata, media_body=media, fields='id'
        ).execute()
        file_id = uploaded['id']

        # Clean up temp file
        os.unlink(tmp_path)

        logger.info(
            "backup_database_to_drive: uploaded %s (%s bytes) as %s",
            backup_name, file_size, file_id,
        )

        # ----- Rotate old backups -----
        results = drive_svc.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields='files(id, name, createdTime)',
            orderBy='createdTime',
            pageSize=100,
        ).execute()
        files = results.get('files', [])

        backups_retained = len(files)
        if backups_retained > max_backups:
            to_delete = files[:backups_retained - max_backups]
            for old_file in to_delete:
                try:
                    drive_svc.files().delete(fileId=old_file['id']).execute()
                    logger.info(
                        "backup_database_to_drive: deleted old backup %s (%s)",
                        old_file['name'], old_file['id'],
                    )
                except Exception as e:
                    logger.warning(
                        "backup_database_to_drive: failed to delete %s: %s",
                        old_file['id'], e,
                    )
            backups_retained = max_backups

        # ----- Update app_state -----
        state = StateManager()
        state.set_app_state('last_drive_backup_date', now.strftime('%Y-%m-%d'))
        state.set_app_state('last_drive_backup_time', now.strftime('%H:%M:%S'))
        state.set_app_state('last_drive_backup_file_id', file_id)
        state.set_app_state('last_drive_backup_size', str(file_size))

        return {
            "ok": True,
            "file_id": file_id,
            "size_bytes": file_size,
            "backups_retained": backups_retained,
        }

    except Exception as e:
        logger.error("backup_database_to_drive: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}


def get_backup_status() -> dict:
    """Return the status of the most recent Drive backup from app_state."""
    state = StateManager()
    return {
        "last_drive_backup_date": state.get_app_state('last_drive_backup_date'),
        "last_drive_backup_time": state.get_app_state('last_drive_backup_time'),
        "last_drive_backup_file_id": state.get_app_state('last_drive_backup_file_id'),
        "last_drive_backup_size": state.get_app_state('last_drive_backup_size'),
    }
