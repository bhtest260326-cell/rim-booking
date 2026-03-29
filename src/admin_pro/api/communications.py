import re
import logging

from flask import Blueprint, jsonify, request
from admin_pro.api import api_response

logger = logging.getLogger(__name__)


def register(bp, require_auth):

    # ------------------------------------------------------------------
    # GET /api/comms/gmail
    # ------------------------------------------------------------------
    @bp.route("/api/comms/gmail", methods=["GET"])
    @require_auth
    def comms_gmail():
        try:
            limit = min(100, max(1, int(request.args.get("limit", 20))))
        except (ValueError, TypeError):
            limit = 20
        try:
            from google_auth import get_gmail_service

            service = get_gmail_service()
            result = (
                service.users()
                .messages()
                .list(userId="me", maxResults=limit, labelIds=["INBOX"])
                .execute()
            )
            raw_messages = result.get("messages", [])

            messages = []
            for msg_stub in raw_messages:
                msg_id = msg_stub["id"]
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="metadata",
                         metadataHeaders=["Subject", "From", "Date"])
                    .execute()
                )
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                messages.append(
                    {
                        "id": msg_id,
                        "subject": headers.get("Subject", ""),
                        "from": headers.get("From", ""),
                        "date": headers.get("Date", ""),
                        "snippet": msg.get("snippet", ""),
                    }
                )

            return api_response(data={"messages": messages})
        except Exception:
            logger.exception("comms_gmail error detail")
            return api_response(error="Gmail unavailable", code="SERVICE_UNAVAILABLE", status=503)

    # ------------------------------------------------------------------
    # GET /api/comms/dlq
    # ------------------------------------------------------------------
    @bp.route("/api/comms/dlq", methods=["GET"])
    @require_auth
    def comms_dlq():
        try:
            from state_manager import _get_conn

            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM failed_extractions ORDER BY last_failed_at DESC LIMIT 50"
                ).fetchall()

            entries = [
                {
                    "id": row["id"],
                    "gmail_msg_id": row["gmail_msg_id"],
                    "customer_email": row["customer_email"],
                    "error_type": row["error_type"],
                    "error_message": row["error_message"],
                    "failure_count": row["failure_count"],
                    "first_failed_at": row["first_failed_at"],
                    "last_failed_at": row["last_failed_at"],
                    "owner_notified": row["owner_notified"],
                }
                for row in rows
            ]
            return api_response(data={"entries": entries})
        except Exception:
            logger.exception("comms_dlq error")
            return api_response(error="Failed to fetch DLQ entries", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # POST /api/comms/dlq/<msg_id>/dismiss
    # ------------------------------------------------------------------
    @bp.route("/api/comms/dlq/<msg_id>/dismiss", methods=["POST"])
    @require_auth
    def comms_dlq_dismiss(msg_id):
        try:
            from state_manager import _get_conn

            with _get_conn() as conn:
                conn.execute(
                    "UPDATE failed_extractions SET owner_notified=1 WHERE gmail_msg_id=?",
                    (msg_id,),
                )
            return api_response()
        except Exception:
            logger.exception("comms_dlq_dismiss error for %s", msg_id)
            return api_response(error="Failed to dismiss entry", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # POST /api/comms/sms
    # ------------------------------------------------------------------
    @bp.route("/api/comms/sms", methods=["POST"])
    @require_auth
    def comms_send_sms():
        try:
            body = request.get_json(force=True) or {}
            to = body.get("to", "").strip()
            message = body.get("message", "").strip()

            if not to or not message:
                return api_response(error="Both 'to' and 'message' are required", code="VALIDATION_ERROR", status=400)

            if not re.match(r'^\+?61[45]\d{8}$', to.replace(' ', '')):
                return api_response(error="Invalid Australian mobile number", code="VALIDATION_ERROR", status=400)
            if len(message) > 1600:
                return api_response(error="Message too long (max 1600 chars)", code="VALIDATION_ERROR", status=400)

            from twilio_handler import send_sms

            send_sms(to, message)
            return api_response()
        except Exception:
            logger.exception("comms_send_sms error")
            return api_response(error="Failed to send SMS", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # GET /api/comms/clarifications
    # ------------------------------------------------------------------
    @bp.route("/api/comms/clarifications", methods=["GET"])
    @require_auth
    def comms_clarifications():
        try:
            from state_manager import _get_conn

            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM clarifications ORDER BY created_at DESC"
                ).fetchall()

            clarifications = [
                {
                    "id": row["id"],
                    "customer_email": row["customer_email"],
                    "missing_fields": row["missing_fields"],
                    "attempt_count": row["attempt_count"],
                    "created_at": row["created_at"],
                    "thread_id": row["thread_id"],
                }
                for row in rows
            ]
            return api_response(data={"clarifications": clarifications})
        except Exception:
            logger.exception("comms_clarifications error")
            return api_response(error="Failed to fetch clarifications", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # GET /api/comms/waitlist
    # ------------------------------------------------------------------
    @bp.route("/api/comms/waitlist", methods=["GET"])
    @require_auth
    def comms_waitlist():
        try:
            from state_manager import _get_conn

            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM waitlist ORDER BY created_at DESC"
                ).fetchall()

            waitlist = [
                {
                    "id": row["id"],
                    "customer_email": row["customer_email"],
                    "customer_name": row["customer_name"],
                    "requested_date": row["requested_date"],
                    "notified": row["notified"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
            return api_response(data={"waitlist": waitlist})
        except Exception:
            logger.exception("comms_waitlist error")
            return api_response(error="Failed to fetch waitlist", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # POST /api/comms/waitlist/<waitlist_id>/notify
    # ------------------------------------------------------------------
    @bp.route("/api/comms/waitlist/<int:waitlist_id>/notify", methods=["POST"])
    @require_auth
    def comms_waitlist_notify(waitlist_id):
        try:
            from state_manager import _get_conn

            with _get_conn() as conn:
                conn.execute(
                    "UPDATE waitlist SET notified=1 WHERE id=?",
                    (waitlist_id,),
                )
            return api_response()
        except Exception:
            logger.exception("comms_waitlist_notify error for id %s", waitlist_id)
            return api_response(error="Failed to update waitlist entry", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # GET /api/comms/sms/log
    # ------------------------------------------------------------------
    @bp.route("/api/comms/sms/log", methods=["GET"])
    @require_auth
    def comms_sms_log():
        """Return recent outbound SMS from sms_log table (if it exists)."""
        try:
            limit = min(200, max(1, int(request.args.get("limit", 20))))
        except (ValueError, TypeError):
            limit = 20
        try:
            from state_manager import _get_conn
            with _get_conn() as conn:
                # sms_log may not exist in all deployments — handle gracefully
                rows = conn.execute(
                    "SELECT * FROM sms_log ORDER BY sent_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            logs = [dict(row) for row in rows]
            return api_response(data={"logs": logs})
        except Exception:
            return api_response(data={"logs": []})

    # ------------------------------------------------------------------
    # GET /api/comms/activity
    # ------------------------------------------------------------------
    @bp.route("/api/comms/activity", methods=["GET"])
    @require_auth
    def comms_activity():
        try:
            limit = min(200, max(1, int(request.args.get("limit", 50))))
        except (ValueError, TypeError):
            limit = 50
        try:
            from state_manager import _get_conn

            with _get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT be.id, be.booking_id, be.event_type, be.actor,
                           be.details, be.created_at, b.customer_email
                    FROM booking_events be
                    LEFT JOIN bookings b ON b.id = be.booking_id
                    ORDER BY be.created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

            events = [
                {
                    "id": row["id"],
                    "booking_id": row["booking_id"],
                    "event_type": row["event_type"],
                    "actor": row["actor"],
                    "details": row["details"],
                    "created_at": row["created_at"],
                    "customer_email": row["customer_email"],
                }
                for row in rows
            ]
            return api_response(data={"events": events})
        except Exception:
            logger.exception("comms_activity error")
            return api_response(error="Failed to fetch activity", code="INTERNAL_ERROR", status=500)


# Self-registration when module is imported directly
from admin_pro import admin_pro_bp, require_auth  # noqa: E402

register(admin_pro_bp, require_auth)
