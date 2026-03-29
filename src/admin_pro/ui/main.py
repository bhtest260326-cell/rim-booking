"""admin_pro/ui/main.py — Assembles and serves the admin pro SPA."""
import logging
import secrets
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
<title>Wheel Doctor — Control Pro</title>
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#C41230">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<script>
if ('serviceWorker' in navigator) {{
  navigator.serviceWorker.register('/static/sw.js').catch(function(err) {{ console.warn('SW:', err); }});
}}
</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
{CSS}
</style>
</head>
<body class="ap-body">
<div class="ap-sidebar-overlay" id="ap-sidebar-overlay" onclick="closeSidebarMobile()"></div>
{HTML_SIDEBAR}
<div class="ap-main" id="ap-main">
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
                return "<h1>Internal Error</h1><pre>An error occurred. Check server logs.</pre>", 500

        html = _CACHED_HTML

        # Create a session cookie so that all API fetch() calls from this
        # browser are automatically authenticated (cookie is sent same-origin).
        from admin_pro import _create_session
        sid = _create_session()
        csrf_token = secrets.token_hex(32)

        resp = Response(html, mimetype='text/html')
        # Prevent browser/CDN caching so every deploy serves fresh HTML+JS
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        # Security headers
        resp.headers['X-Frame-Options'] = 'DENY'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        import os as _os
        on_railway = bool(_os.environ.get('RAILWAY_ENVIRONMENT') or
                          _os.environ.get('RAILWAY_SERVICE_NAME'))
        if on_railway:
            resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        resp.set_cookie(
            'ap_session', sid,
            max_age=28800,   # 8 hours
            httponly=True,
            samesite='Strict',
            secure=on_railway,
        )
        # CSRF token — JS-readable so fetch() can send it as X-CSRF-Token header
        resp.set_cookie(
            'ap_csrf', csrf_token,
            max_age=28800,
            httponly=False,
            samesite='Strict',
            secure=on_railway,
        )
        return resp

    @bp.route('/refresh-cache', methods=['POST'])
    @require_auth
    def refresh_cache():
        global _CACHED_HTML
        _CACHED_HTML = None
        from flask import jsonify
        return jsonify({'ok': True, 'message': 'Cache cleared'})
