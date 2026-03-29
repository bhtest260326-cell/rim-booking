"""
admin_pro/api/system.py — System health, flags, DB stats, app state, and day cancellation.
"""

import os
import sqlite3
import logging

from flask import jsonify, request
from admin_pro.api import api_response

logger = logging.getLogger(__name__)

# Resolve the SQLite DB path using the same logic as state_manager.py
_STATE_FILE_JSON = os.environ.get('STATE_FILE', '/data/booking_state.json')
DB_PATH = os.path.splitext(_STATE_FILE_JSON)[0] + '.db'


def register(bp, require_auth):

    # ------------------------------------------------------------------
    # GET /api/system/health
    # ------------------------------------------------------------------

    @bp.route('/api/system/health', methods=['GET'])
    @require_auth
    def system_health():
        result = {}

        # --- DB check ---
        try:
            size_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 3) if os.path.exists(DB_PATH) else 0.0
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()
            bookings_count = row[0] if row else 0
            conn.close()
            db_status = {'status': 'ok', 'size_mb': size_mb, 'bookings_count': bookings_count}
        except Exception as e:
            logger.warning('DB health check failed: %s', e)
            db_status = {'status': 'error', 'size_mb': 0.0, 'bookings_count': 0}

        result['db'] = db_status

        # --- Gmail check ---
        try:
            refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN', '')
            if not refresh_token:
                gmail_status = {'status': 'unconfigured', 'last_poll': None}
            else:
                conn = sqlite3.connect(DB_PATH, timeout=5)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT value FROM app_state WHERE key='last_gmail_poll_at'"
                ).fetchone()
                conn.close()
                last_poll = row['value'] if row else None
                gmail_status = {'status': 'ok', 'last_poll': last_poll}
        except Exception as e:
            logger.warning('Gmail health check failed: %s', e)
            gmail_status = {'status': 'error', 'last_poll': None}

        result['gmail'] = gmail_status

        # --- Anthropic check ---
        result['anthropic'] = {
            'status': 'configured' if os.environ.get('ANTHROPIC_API_KEY') else 'unconfigured'
        }

        # --- Twilio check ---
        result['twilio'] = {
            'status': 'configured' if os.environ.get('TWILIO_ACCOUNT_SID') else 'unconfigured'
        }

        # --- Uptime / mode info ---
        pubsub_mode = bool(os.environ.get('PUBSUB_TOPIC_NAME', ''))
        result['uptime_info'] = {'pubsub_mode': pubsub_mode}

        result['status'] = 'ok'
        return api_response(data=result)

    # ------------------------------------------------------------------
    # GET /api/system/flags
    # ------------------------------------------------------------------

    @bp.route('/api/system/flags', methods=['GET'])
    @require_auth
    def get_flags():
        try:
            from feature_flags import get_all_flags
            return api_response(data={'flags': get_all_flags()})
        except Exception:
            logger.exception('get_flags error')
            return api_response(error='Internal server error', code='INTERNAL_ERROR', status=500)

    # ------------------------------------------------------------------
    # POST /api/system/flags/<key>
    # ------------------------------------------------------------------

    @bp.route('/api/system/flags/<key>', methods=['POST'])
    @require_auth
    def set_flag_route(key):
        try:
            from feature_flags import set_flag, FLAGS
            if key not in FLAGS:
                return api_response(error=f'Unknown flag: {key}', code='NOT_FOUND', status=400)
            body = request.get_json(force=True, silent=True) or {}
            enabled = bool(body.get('enabled', True))
            set_flag(key, enabled)
            return api_response(data={'key': key, 'enabled': enabled})
        except Exception:
            logger.exception('set_flag error')
            return api_response(error='Internal server error', code='INTERNAL_ERROR', status=500)

    # ------------------------------------------------------------------
    # GET /api/system/db-stats
    # ------------------------------------------------------------------

    # Allowlist of known tables — prevents dynamic SQL on unexpected table names
    _ALLOWED_TABLES = {
        'bookings', 'clarifications', 'processed_emails', 'processed_sms',
        'app_state', 'booking_events', 'failed_extractions',
        'customer_service_history', 'waitlist', 'message_queue',
        'data_retention_log', 'sms_log',
    }

    @bp.route('/api/system/db-stats', methods=['GET'])
    @require_auth
    def db_stats():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            tables_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            tables = []
            total_rows = 0
            for (name,) in tables_rows:
                if name not in _ALLOWED_TABLES:
                    continue  # Skip any unexpected tables
                try:
                    count_row = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()
                    count = count_row[0] if count_row else 0
                except Exception:
                    count = 0
                tables.append({'name': name, 'count': count})
                total_rows += count
            conn.close()
            return api_response(data={'tables': tables, 'total_rows': total_rows})
        except Exception:
            logger.exception('db_stats error')
            return api_response(error='Internal server error', code='INTERNAL_ERROR', status=500)

    # ------------------------------------------------------------------
    # POST /api/system/cancel-day
    # ------------------------------------------------------------------

    @bp.route('/api/system/cancel-day', methods=['POST'])
    @require_auth
    def cancel_day():
        try:
            body = request.get_json(force=True, silent=True) or {}
            date = body.get('date', '').strip()
            reason = body.get('reason', '').strip()
            if not date:
                return api_response(error='date is required', code='VALIDATION_ERROR', status=400)
            from state_manager import StateManager
            state = StateManager()
            cancelled = state.cancel_all_bookings_for_date(date, reason, 'owner_ui')
            return api_response(data={'cancelled': len(cancelled), 'booking_ids': cancelled})
        except Exception:
            logger.exception('cancel_day error')
            return api_response(error='Internal server error', code='INTERNAL_ERROR', status=500)

    # ------------------------------------------------------------------
    # GET /api/system/app-state
    # ------------------------------------------------------------------

    @bp.route('/api/system/app-state', methods=['GET'])
    @require_auth
    def get_app_state_all():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT key, value FROM app_state ORDER BY key').fetchall()
            conn.close()
            state = {row['key']: row['value'] for row in rows}
            return api_response(data={'state': state})
        except Exception:
            logger.exception('get_app_state error')
            return api_response(error='Internal server error', code='INTERNAL_ERROR', status=500)

    # ------------------------------------------------------------------
    # POST /api/system/app-state/<key>
    # ------------------------------------------------------------------

    _BLOCKED_STATE_KEYS = {'booking_counter', 'json_migration_done', 'gmail_history_id', 'ratelimit_'}

    @bp.route('/api/system/app-state/<key>', methods=['POST'])
    @require_auth
    def set_app_state_route(key):
        try:
            if any(key == bk or key.startswith(bk) for bk in _BLOCKED_STATE_KEYS):
                return api_response(error='This key cannot be modified via API', code='FORBIDDEN', status=403)
            body = request.get_json(force=True, silent=True) or {}
            value = body.get('value', '')
            from state_manager import StateManager
            StateManager().set_app_state(key, value)
            return api_response(data={'key': key, 'value': value})
        except Exception:
            logger.exception('set_app_state error')
            return api_response(error='Internal server error', code='INTERNAL_ERROR', status=500)

    # ------------------------------------------------------------------
    # GET /api/system/waitlist
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # GET /api/system/backup-status
    # ------------------------------------------------------------------

    @bp.route("/api/system/backup-status", methods=["GET"])
    @require_auth
    def backup_status():
        """Return the current backup status from app_state."""
        try:
            from backup_handler import get_backup_status
            status = get_backup_status()
            return api_response(data=status)
        except Exception:
            logger.exception("Error fetching backup status")
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # POST /api/system/backup-now
    # ------------------------------------------------------------------

    @bp.route("/api/system/backup-now", methods=["POST"])
    @require_auth
    def backup_now():
        """Trigger an immediate backup to Google Drive."""
        try:
            from backup_handler import backup_database_to_drive
            result = backup_database_to_drive()
            return api_response(data=result)
        except Exception:
            logger.exception("Error triggering backup")
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # GET /api/system/waitlist
    # ------------------------------------------------------------------

    @bp.route('/api/system/waitlist', methods=['GET'])
    @require_auth
    def get_waitlist():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM waitlist ORDER BY created_at DESC'
            ).fetchall()
            conn.close()
            entries = [dict(row) for row in rows]
            return api_response(data={'waitlist': entries, 'total': len(entries)})
        except Exception:
            logger.exception('get_waitlist error')
            return api_response(error='Internal server error', code='INTERNAL_ERROR', status=500)


# ---------------------------------------------------------------------------
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
