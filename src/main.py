import os
import sys
import time
import threading
import logging
from pythonjsonlogger import jsonlogger
from webhook_server import create_app
from gmail_poller import poll_gmail, register_gmail_watch
from twilio_handler import poll_sms_replies
from scheduler import run_scheduled_tasks


def _configure_logging():
    """Configure structured JSON logging for production (Railway) deployment."""
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()

    # JSON formatter — every log line is a parseable JSON object
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
        rename_fields={'asctime': 'ts', 'name': 'logger', 'levelname': 'level'}
    )

    # Apply to root logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))

    # Quieten noisy third-party loggers
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
    logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


def _validate_env():
    """On Railway, ensure critical security env vars are set."""
    if not os.environ.get('RAILWAY_ENVIRONMENT'):
        return
    missing = []
    for var in ('ADMIN_PASSWORD', 'RESCHEDULE_SECRET'):
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        raise RuntimeError(
            f"Missing required env var(s) on Railway: {', '.join(missing)}"
        )


PUBSUB_ENABLED = bool(os.environ.get('PUBSUB_TOPIC_NAME', ''))

# Gmail watches expire after 7 days — renew every 6 to be safe
_WATCH_RENEWAL_INTERVAL = 6 * 24 * 3600


def _background_loop():
    """Runs in a daemon thread alongside the Flask server.

    - When Pub/Sub is enabled: only runs scheduled tasks + renews the Gmail watch.
    - When Pub/Sub is disabled: also polls Gmail and Twilio every 60 s (legacy mode).
    """
    last_watch_renewal = 0

    while True:
        try:
            now = time.time()

            # Renew Gmail watch every 6 days
            if PUBSUB_ENABLED and (now - last_watch_renewal > _WATCH_RENEWAL_INTERVAL):
                register_gmail_watch()
                last_watch_renewal = now

            # Legacy polling fallback
            if not PUBSUB_ENABLED:
                poll_gmail()
                try:
                    from state_manager import StateManager
                    from datetime import datetime, timezone
                    StateManager().set_app_state('last_gmail_poll_at', datetime.now(timezone.utc).isoformat())
                except Exception:
                    pass
                poll_sms_replies()

            run_scheduled_tasks()

        except Exception as e:
            logger.error(f"Background loop error: {e}", exc_info=True)

        time.sleep(30)


def main():
    _configure_logging()
    _validate_env()
    logger.info("Wheel Doctor Booking System starting...")

    if PUBSUB_ENABLED:
        logger.info("Pub/Sub mode: real-time Gmail webhooks enabled")
        register_gmail_watch()
    else:
        logger.info("Polling mode: no PUBSUB_TOPIC_NAME set, using 60-second poll")

    # Start background thread (scheduled tasks + optional polling)
    bg = threading.Thread(target=_background_loop, daemon=True, name="background")
    bg.start()

    # Start Flask — Railway routes HTTP traffic to $PORT
    port = int(os.environ.get('PORT', 8080))
    app = create_app()
    logger.info(f"Webhook server listening on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)


if __name__ == '__main__':
    main()
