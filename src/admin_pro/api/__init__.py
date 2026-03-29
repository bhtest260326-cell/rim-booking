# admin_pro.api package

from flask import jsonify


def api_response(data=None, error=None, code=None, status=200):
    """Build a consistent API response.

    Success: {"ok": true, "data": {...}}
    Error:   {"ok": false, "error": "message", "code": "ERROR_CODE"}

    For backward compatibility the *data* dict is also merged into the
    top-level response so existing frontend code that checks for specific
    fields (e.g. ``response.bookings``) continues to work.
    """
    if error is not None:
        payload = {"ok": False, "error": error}
        if code:
            payload["code"] = code
        return jsonify(payload), status

    payload = {"ok": True, "data": data or {}}
    # Merge data keys at top level for backward compat
    if isinstance(data, dict):
        payload.update(data)
    return jsonify(payload), status
