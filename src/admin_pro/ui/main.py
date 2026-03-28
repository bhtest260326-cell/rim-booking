"""admin_pro/ui/main.py — Assembles and serves the admin pro SPA."""
import logging
logger = logging.getLogger(__name__)

def _build_html():
    from .css import CSS
    from .html import HTML_SIDEBAR, HTML_TOPBAR, HTML_SECTIONS, HTML_MODALS
    from .js_core import JS_CORE
    from .js_dashboard import JS_DASHBOARD
    from .js_bookings import JS_BOOKINGS
    from .js_analytics import JS_ANALYTICS
    from .js_calendar import JS_CALENDAR
    from .js_comms import JS_COMMS
    from .js_system import JS_SYSTEM
    from .js_activity import JS_ACTIVITY
    from .js_customers import JS_CUSTOMERS

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rim Repair — Control Pro</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
{CSS}
</style>
</head>
<body class="ap-body">
{HTML_SIDEBAR}
<div class="ap-main-wrapper">
{HTML_TOPBAR}
<main class="ap-content">
{HTML_SECTIONS}
</main>
</div>
{HTML_MODALS}
<script>
{JS_CORE}
{JS_DASHBOARD}
{JS_BOOKINGS}
{JS_ANALYTICS}
{JS_CALENDAR}
{JS_COMMS}
{JS_SYSTEM}
{JS_ACTIVITY}
{JS_CUSTOMERS}
</script>
</body>
</html>"""

_CACHED_HTML = None

def register(bp, require_auth):
    from flask import Response, request

    @bp.route('/', methods=['GET'])
    @require_auth
    def serve_spa():
        global _CACHED_HTML
        # Cache busting: ?refresh=1 forces rebuild
        if _CACHED_HTML is None or request.args.get('refresh'):
            try:
                _CACHED_HTML = _build_html()
                logger.info("Admin Pro SPA built and cached")
            except Exception as e:
                logger.error(f"SPA build failed: {e}", exc_info=True)
                return f"<h1>Build Error</h1><pre>{e}</pre>", 500

        html = _CACHED_HTML

        # Create a session cookie so that all API fetch() calls from this
        # browser are automatically authenticated (cookie is sent same-origin).
        from admin_pro import _create_session
        sid = _create_session()

        resp = Response(html, mimetype='text/html')
        resp.set_cookie(
            'ap_session', sid,
            max_age=86400,   # 24 hours
            httponly=True,
            samesite='Strict',
        )
        return resp

    @bp.route('/refresh-cache', methods=['POST'])
    @require_auth
    def refresh_cache():
        global _CACHED_HTML
        _CACHED_HTML = None
        from flask import jsonify
        return jsonify({'ok': True, 'message': 'Cache cleared'})
