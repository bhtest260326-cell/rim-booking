import json
import base64
import logging
from flask import jsonify, request
from state_manager import _get_conn

logger = logging.getLogger(__name__)


def register(bp, require_auth):

    @bp.route("/api/customers", methods=["GET"])
    @require_auth
    def list_customers():
        try:
            with _get_conn() as conn:
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
                    """
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

            return jsonify({"customers": customers, "total": len(customers)})
        except Exception:
            logger.exception("Error listing customers")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/customers/search", methods=["GET"])
    @require_auth
    def search_customers():
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"results": []})

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

            return jsonify({"results": results})
        except Exception:
            logger.exception("Error searching customers")
            return jsonify({"error": "Internal server error"}), 500

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
            return jsonify({"history": history})
        except Exception:
            logger.exception("Error fetching service history")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/customers/<email_b64>", methods=["GET"])
    @require_auth
    def customer_profile(email_b64):
        try:
            # Decode base64url-encoded email
            padding = 4 - len(email_b64) % 4
            if padding != 4:
                email_b64 += "=" * padding
            email = base64.urlsafe_b64decode(email_b64).decode("utf-8")
        except Exception:
            return jsonify({"error": "Invalid email encoding"}), 400

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
                    return jsonify({"error": "Customer not found"}), 404

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

            return jsonify(
                {
                    "email": email,
                    "name": name,
                    "phone": phone,
                    "stats": stats,
                    "bookings": bookings,
                    "service_history": service_history,
                    "maintenance_due": maintenance_due,
                }
            )
        except Exception:
            logger.exception("Error fetching customer profile for %s", email)
            return jsonify({"error": "Internal server error"}), 500


from admin_pro import admin_pro_bp, require_auth  # noqa: E402

register(admin_pro_bp, require_auth)
