import os
import time
import hmac
import secrets
import functools
import logging
from collections import defaultdict

from flask import Blueprint, jsonify, request, make_response

logger = logging.getLogger(__name__)

admin_pro_bp = Blueprint('admin_pro', __name__, url_prefix='/v2')

# In-memory session store: session_id -> expiry unix timestamp.
# Sessions expire after 24 hours. Cleared on process restart (Railway redeploy).
_SESSIONS: dict = {}
_SESSION_TTL = 86400  # 24 hours

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter for brute-force protection.
# Tracks failed auth attempts per IP: {ip: [timestamp, ...]}
# After _RATE_LIMIT_MAX failures in _RATE_LIMIT_WINDOW seconds the IP is
# blocked for _RATE_LIMIT_BLOCK_SECS seconds.
# ---------------------------------------------------------------------------
_RATE_LIMIT_WINDOW = 60       # seconds to count failures in
_RATE_LIMIT_MAX = 10          # max failures before block
_RATE_LIMIT_BLOCK_SECS = 300  # 5-minute block
_rate_fail_times: dict = defaultdict(list)   # ip -> [unix_ts, ...]
_rate_blocked_until: dict = {}               # ip -> unix_ts


def _rate_limit_check(ip: str) -> bool:
    """Return True if the IP is currently rate-limited (should be blocked)."""
    now = time.time()
    blocked_until = _rate_blocked_until.get(ip, 0)
    if now < blocked_until:
        return True
    return False


def _rate_limit_record_failure(ip: str) -> None:
    """Record a failed auth attempt for *ip*; apply block if threshold exceeded."""
    now = time.time()
    # Prune old timestamps outside the window
    _rate_fail_times[ip] = [t for t in _rate_fail_times[ip] if now - t < _RATE_LIMIT_WINDOW]
    _rate_fail_times[ip].append(now)
    if len(_rate_fail_times[ip]) >= _RATE_LIMIT_MAX:
        _rate_blocked_until[ip] = now + _RATE_LIMIT_BLOCK_SECS
        logger.warning("Rate-limit: blocked IP %s for %ds after %d failures",
                       ip, _RATE_LIMIT_BLOCK_SECS, len(_rate_fail_times[ip]))
        _rate_fail_times[ip] = []  # reset counter after block is applied


def _rate_limit_clear(ip: str) -> None:
    """Clear failure history for *ip* after a successful authentication."""
    _rate_fail_times.pop(ip, None)
    _rate_blocked_until.pop(ip, None)


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
    """Check if the current request carries valid Basic Auth or token credentials.

    All secret comparisons use hmac.compare_digest to prevent timing attacks.
    """
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_token = os.environ.get('ADMIN_TOKEN', '')

    # No security configured — dev mode
    if not admin_password and not admin_token:
        return True

    # Token query param — constant-time comparison
    if admin_token:
        supplied_token = request.args.get('token', '')
        if hmac.compare_digest(supplied_token.encode(), admin_token.encode()):
            return True

    # HTTP Basic Auth — constant-time comparison for both username and password
    if admin_password:
        auth = request.authorization
        if auth:
            username_ok = hmac.compare_digest(
                (auth.username or '').encode(), admin_username.encode()
            )
            password_ok = hmac.compare_digest(
                (auth.password or '').encode(), admin_password.encode()
            )
            if username_ok and password_ok:
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

        # Determine client IP for rate limiting
        client_ip = (
            request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr
            or 'unknown'
        )

        # Check if IP is currently rate-limited
        if _rate_limit_check(client_ip):
            logger.warning("Rate-limit: rejected request from %s", client_ip)
            return make_response(
                jsonify({'ok': False, 'error': 'Too many failed attempts. Try again later.'}),
                429
            )

        # Check session cookie first (set after successful login on the SPA page)
        sid = request.cookies.get('ap_session', '')
        if sid and _check_session(sid):
            return f(*args, **kwargs)

        # Fall back to direct credentials (Basic Auth or ?token=)
        if _credentials_valid():
            _rate_limit_clear(client_ip)
            return f(*args, **kwargs)

        # Unauthorized — record failure for rate limiting
        _rate_limit_record_failure(client_ip)
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
