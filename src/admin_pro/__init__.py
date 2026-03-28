import os
import time
import secrets
import functools
import logging

from flask import Blueprint, jsonify, request, make_response

logger = logging.getLogger(__name__)

admin_pro_bp = Blueprint('admin_pro', __name__, url_prefix='/v2')

# In-memory session store: session_id -> expiry unix timestamp.
# Sessions expire after 24 hours. Cleared on process restart (Railway redeploy).
_SESSIONS: dict = {}
_SESSION_TTL = 86400  # 24 hours


def _create_session() -> str:
    sid = secrets.token_hex(20)
    _SESSIONS[sid] = time.time() + _SESSION_TTL
    # Prune expired sessions to avoid unbounded growth
    now = time.time()
    expired = [k for k, v in _SESSIONS.items() if v < now]
    for k in expired:
        del _SESSIONS[k]
    return sid


def _check_session(sid: str) -> bool:
    expiry = _SESSIONS.get(sid, 0)
    return time.time() < expiry


def _credentials_valid() -> bool:
    """Check if the current request carries valid Basic Auth or token credentials."""
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_token = os.environ.get('ADMIN_TOKEN', '')

    # No security configured — dev mode
    if not admin_password and not admin_token:
        return True

    # Token query param
    if admin_token and request.args.get('token', '') == admin_token:
        return True

    # HTTP Basic Auth
    if admin_password:
        auth = request.authorization
        if auth and auth.username == admin_username and auth.password == admin_password:
            return True

    return False


def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        admin_password = os.environ.get('ADMIN_PASSWORD', '')
        admin_token = os.environ.get('ADMIN_TOKEN', '')

        # Dev mode — no auth configured
        if not admin_password and not admin_token:
            return f(*args, **kwargs)

        # Check session cookie first (set after successful login on the SPA page)
        sid = request.cookies.get('ap_session', '')
        if sid and _check_session(sid):
            return f(*args, **kwargs)

        # Fall back to direct credentials (Basic Auth or ?token=)
        if _credentials_valid():
            return f(*args, **kwargs)

        # Unauthorized
        response = make_response(
            jsonify({'ok': False, 'error': 'Unauthorized'}),
            401
        )
        if admin_password:
            response.headers['WWW-Authenticate'] = 'Basic realm="Admin"'
        return response

    return decorated


def json_ok(data):
    return jsonify({'ok': True, 'data': data})


def json_err(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code


# Import sub-modules last so that blueprint and helpers are defined before
# registration. Each module calls register(admin_pro_bp, require_auth) at
# import time.
from .api import bookings, analytics, communications, system, customers  # noqa: F401, E402
from .ui import main as ui_main  # noqa: F401, E402
ui_main.register(admin_pro_bp, require_auth)  # register SPA route
