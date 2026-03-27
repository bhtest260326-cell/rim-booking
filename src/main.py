import os
import time
import threading
import logging
from webhook_server import create_app
from gmail_poller import poll_gmail, register_gmail_watch
from twilio_handler import poll_sms_replies
from scheduler import run_scheduled_tasks

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

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
    logger.info("Rim Repair Booking System starting...")

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
