import re
import json
import uuid
import base64
import logging
from datetime import datetime, timezone
from flask import jsonify, request
from state_manager import _get_conn
from admin_pro.api import api_response

logger = logging.getLogger(__name__)


def register(bp, require_auth):

    @bp.route("/api/customers", methods=["GET"])
    @require_auth
    def list_customers():
        try:
            # Pagination params
            try:
                page = max(1, int(request.args.get("page", 1)))
            except (ValueError, TypeError):
                page = 1
            try:
                per_page = min(200, max(1, int(request.args.get("per_page", 50))))
            except (ValueError, TypeError):
                per_page = 50

            with _get_conn() as conn:
                # Get total count
                total = conn.execute(
                    """
                    SELECT COUNT(*) as cnt FROM (
                        SELECT customer_email
                        FROM bookings
                        WHERE customer_email IS NOT NULL AND customer_email != ''
                        GROUP BY customer_email
                    )
                    """
                ).fetchone()["cnt"]

                # Get paginated results
                offset = (page - 1) * per_page
                rows = conn.execute(
                    """
                    SELECT customer_email,
                           COUNT(*) as total_bookings,
                           SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) as confirmed,
                           MAX(created_at) as last_booking,
                           MIN(created_at) as first_booking
                    FROM bookings
                    WHERE customer_email IS NOT NULL AND customer_email != ''
                    GROUP BY customer_email
                    ORDER BY last_booking DESC
                    LIMIT ? OFFSET ?
                    """,
                    (per_page, offset),
                ).fetchall()

                customers = []
                for row in rows:
                    email = row["customer_email"]
                    name = None
                    phone = None

                    # Parse most recent booking_data for name/phone
                    recent = conn.execute(
                        """
                        SELECT booking_data FROM bookings
                        WHERE customer_email = ?
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (email,),
                    ).fetchone()
                    if recent and recent["booking_data"]:
                        try:
                            bd = json.loads(recent["booking_data"])
                            name = bd.get("customer_name") or bd.get("name")
                            phone = bd.get("phone") or bd.get("customer_phone")
                        except (json.JSONDecodeError, TypeError):
                            pass

                    customers.append(
                        {
                            "email": email,
                            "name": name,
                            "phone": phone,
                            "total_bookings": row["total_bookings"],
                            "confirmed": row["confirmed"] or 0,
                            "last_booking": row["last_booking"],
                            "first_booking": row["first_booking"],
                        }
                    )

            pages = max(1, (total + per_page - 1) // per_page)
            return api_response(data={
                "customers": customers,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": pages,
            })
        except Exception:
            logger.exception("Error listing customers")
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)

    @bp.route("/api/customers/search", methods=["GET"])
    @require_auth
    def search_customers():
        q = request.args.get("q", "").strip()
        if not q:
            return api_response(data={"results": []})
        if len(q) > 100:
            q = q[:100]  # Cap query length to prevent expensive LIKE scans

        try:
            with _get_conn() as conn:
                like = f"%{q}%"

                rows = conn.execute(
                    """
                    SELECT customer_email,
                           COUNT(*) as booking_count,
                           MAX(created_at) as last_booking
                    FROM bookings
                    WHERE customer_email IS NOT NULL AND customer_email != ''
                      AND (
                        customer_email LIKE ?
                        OR booking_data LIKE ?
                      )
                    GROUP BY customer_email
                    ORDER BY last_booking DESC
                    """,
                    (like, like),
                ).fetchall()

                results = []
                for row in rows:
                    email = row["customer_email"]
                    name = None
                    phone = None

                    recent = conn.execute(
                        """
                        SELECT booking_data FROM bookings
                        WHERE customer_email = ?
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (email,),
                    ).fetchone()
                    if recent and recent["booking_data"]:
                        try:
                            bd = json.loads(recent["booking_data"])
                            name = bd.get("customer_name") or bd.get("name")
                            phone = bd.get("phone") or bd.get("customer_phone")
                        except (json.JSONDecodeError, TypeError):
                            pass

                    results.append(
                        {
                            "email": email,
                            "name": name,
                            "phone": phone,
                            "booking_count": row["booking_count"],
                        }
                    )

            return api_response(data={"results": results})
        except Exception:
            logger.exception("Error searching customers")
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)

    @bp.route("/api/customers/service-history", methods=["GET"])
    @require_auth
    def all_service_history():
        try:
            with _get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT id, customer_email, vehicle_key, service_type,
                           completed_date, next_reminder_6m, next_reminder_12m,
                           reminder_6m_sent, reminder_12m_sent
                    FROM customer_service_history
                    ORDER BY completed_date DESC
                    """
                ).fetchall()

            history = [dict(row) for row in rows]
            return api_response(data={"history": history})
        except Exception:
            logger.exception("Error fetching service history")
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)

    @bp.route("/api/customers/<email_b64>", methods=["GET"])
    @require_auth
    def customer_profile(email_b64):
        try:
            # Validate identifier length before decoding
            if len(email_b64) > 200:
                return api_response(error="Invalid identifier", code="INVALID_IDENTIFIER", status=400)
            # Decode base64url-encoded email
            padding = 4 - len(email_b64) % 4
            if padding != 4:
                email_b64 += "=" * padding
            email = base64.urlsafe_b64decode(email_b64).decode("utf-8")
            # Basic email format validation
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                return api_response(error="Invalid identifier", code="INVALID_IDENTIFIER", status=400)
        except Exception:
            return api_response(error="Invalid email encoding", code="INVALID_ENCODING", status=400)

        try:
            with _get_conn() as conn:
                # Fetch all bookings for this customer
                booking_rows = conn.execute(
                    """
                    SELECT * FROM bookings
                    WHERE customer_email = ?
                    ORDER BY created_at DESC
                    """,
                    (email,),
                ).fetchall()

                if not booking_rows:
                    return api_response(error="Customer not found", code="NOT_FOUND", status=404)

                bookings = [dict(row) for row in booking_rows]

                # Parse booking_data on each booking
                for b in bookings:
                    if b.get("booking_data"):
                        try:
                            b["booking_data"] = json.loads(b["booking_data"])
                        except (json.JSONDecodeError, TypeError):
                            pass

                # Extract name/phone from most recent booking
                name = None
                phone = None
                most_recent_bd = bookings[0].get("booking_data") if bookings else None
                if isinstance(most_recent_bd, dict):
                    name = most_recent_bd.get("customer_name") or most_recent_bd.get("name")
                    phone = most_recent_bd.get("phone") or most_recent_bd.get("customer_phone")

                # Compute stats
                statuses = [b.get("status", "") for b in bookings]
                stats = {
                    "total": len(bookings),
                    "confirmed": statuses.count("confirmed"),
                    "declined": statuses.count("declined"),
                    "pending": sum(
                        1 for s in statuses if s not in ("confirmed", "declined")
                    ),
                }

                # Service history
                history_rows = conn.execute(
                    """
                    SELECT id, customer_email, vehicle_key, service_type,
                           completed_date, next_reminder_6m, next_reminder_12m,
                           reminder_6m_sent, reminder_12m_sent
                    FROM customer_service_history
                    WHERE customer_email = ?
                    ORDER BY completed_date DESC
                    """,
                    (email,),
                ).fetchall()
                service_history = [dict(row) for row in history_rows]

            # Determine if any maintenance is due
            from datetime import date
            today_str = date.today().isoformat()
            maintenance_due = any(
                (h.get("next_reminder_6m") and h["next_reminder_6m"] <= today_str)
                or (h.get("next_reminder_12m") and h["next_reminder_12m"] <= today_str)
                for h in service_history
            )

            return api_response(data={
                "email": email,
                "name": name,
                "phone": phone,
                "stats": stats,
                "bookings": bookings,
                "service_history": service_history,
                "maintenance_due": maintenance_due,
            })
        except Exception:
            logger.exception("Error fetching customer profile for %s", email)
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)


    # ------------------------------------------------------------------
    # GET /api/gdpr/export/<email_b64> — Export all data for a customer
    # ------------------------------------------------------------------
    @bp.route("/api/gdpr/export/<email_b64>", methods=["GET"])
    @require_auth
    def gdpr_export(email_b64):
        """Export all data held for a customer (GDPR right of access)."""
        try:
            if len(email_b64) > 200:
                return api_response(error="Invalid identifier", code="INVALID_IDENTIFIER", status=400)
            padding = 4 - len(email_b64) % 4
            if padding != 4:
                email_b64 += "=" * padding
            email = base64.urlsafe_b64decode(email_b64).decode("utf-8")
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                return api_response(error="Invalid email", code="INVALID_EMAIL", status=400)
        except Exception:
            return api_response(error="Invalid identifier", code="INVALID_IDENTIFIER", status=400)

        try:
            with _get_conn() as conn:
                bookings = conn.execute(
                    "SELECT id, status, booking_data, created_at, confirmed_at FROM bookings WHERE customer_email=?",
                    (email,)
                ).fetchall()
                clarifications = conn.execute(
                    "SELECT id, missing_fields, attempt_count, created_at FROM clarifications WHERE customer_email=?",
                    (email,)
                ).fetchall()
                events = conn.execute(
                    """SELECT be.booking_id, be.event_type, be.actor, be.created_at
                       FROM booking_events be
                       JOIN bookings b ON be.booking_id = b.id
                       WHERE b.customer_email=?
                       ORDER BY be.created_at DESC""",
                    (email,)
                ).fetchall()

            result = {
                "email": email,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "bookings": [dict(b) for b in bookings],
                "clarifications": [dict(c) for c in clarifications],
                "booking_events": [dict(e) for e in events],
            }
            return api_response(data=result)
        except Exception:
            logger.exception("gdpr_export failed for %s", email_b64)
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)

    # ------------------------------------------------------------------
    # POST /api/gdpr/purge/<email_b64> — Anonymise all PII for a customer
    # ------------------------------------------------------------------
    @bp.route("/api/gdpr/purge/<email_b64>", methods=["POST"])
    @require_auth
    def gdpr_purge(email_b64):
        """Anonymise all PII for a customer (GDPR right to erasure)."""
        try:
            if len(email_b64) > 200:
                return api_response(error="Invalid identifier", code="INVALID_IDENTIFIER", status=400)
            padding = 4 - len(email_b64) % 4
            if padding != 4:
                email_b64 += "=" * padding
            email = base64.urlsafe_b64decode(email_b64).decode("utf-8")
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                return api_response(error="Invalid email", code="INVALID_EMAIL", status=400)
        except Exception:
            return api_response(error="Invalid identifier", code="INVALID_IDENTIFIER", status=400)

        try:
            anon_marker = "[GDPR_PURGED]"
            anon_email = f"purged_{uuid.uuid4().hex[:8]}@gdpr.deleted"

            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, booking_data FROM bookings WHERE customer_email=?", (email,)
                ).fetchall()
                for row in rows:
                    try:
                        bd = json.loads(row["booking_data"]) if row["booking_data"] else {}
                    except Exception:
                        bd = {}
                    for field in ("customer_name", "customer_phone", "address", "customer_email"):
                        if field in bd:
                            bd[field] = anon_marker
                    conn.execute(
                        "UPDATE bookings SET customer_email=?, booking_data=? WHERE id=?",
                        (anon_email, json.dumps(bd), row["id"])
                    )
                # Nullify raw_message on affected bookings
                booking_ids = [row["id"] for row in rows]
                if booking_ids:
                    placeholders = ",".join("?" for _ in booking_ids)
                    conn.execute(
                        f"UPDATE bookings SET raw_message=NULL WHERE id IN ({placeholders})",
                        booking_ids,
                    )
                    # Scrub booking_events.details for affected bookings
                    conn.execute(
                        f"UPDATE booking_events SET details=NULL WHERE booking_id IN ({placeholders})",
                        booking_ids,
                    )
                conn.execute(
                    "UPDATE clarifications SET customer_email=?, booking_data=? WHERE customer_email=?",
                    (anon_email, json.dumps({"purged": True}), email)
                )
                purged_count = len(rows)

            logger.info("GDPR purge completed for %s — %d records anonymised", email, purged_count)
            return api_response(data={"records_anonymised": purged_count})
        except Exception:
            logger.exception("gdpr_purge failed for %s", email_b64)
            return api_response(error="Internal server error", code="INTERNAL_ERROR", status=500)


from admin_pro import admin_pro_bp, require_auth  # noqa: E402

register(admin_pro_bp, require_auth)
