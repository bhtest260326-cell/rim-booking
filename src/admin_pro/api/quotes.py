"""
admin_pro/api/quotes.py — Quote generation and damage scoring API endpoints.
"""

import json
import logging

from flask import request, jsonify

logger = logging.getLogger(__name__)


def register(bp, require_auth):
    """Register quote and damage scoring API routes on *bp*."""

    # ------------------------------------------------------------------
    # POST /api/quotes/generate — generate a quote from booking details
    # ------------------------------------------------------------------
    @bp.route('/api/quotes/generate', methods=['POST'])
    @require_auth
    def generate_quote_endpoint():
        try:
            body = request.get_json(silent=True) or {}

            service_type = body.get('service_type', '')
            rim_count = body.get('rim_count', 1)
            rim_size = body.get('rim_size')
            damage_description = body.get('damage_description', '')
            photos = body.get('photos')  # list of {data, media_type}
            booking_id = body.get('booking_id')

            if not service_type:
                return jsonify({'ok': False, 'error': 'service_type is required'}), 400

            try:
                rim_count = max(1, int(rim_count))
            except (ValueError, TypeError):
                rim_count = 1

            if rim_size is not None:
                try:
                    rim_size = float(rim_size)
                except (ValueError, TypeError):
                    rim_size = None

            from quoting_engine import generate_quote, save_quote

            quote = generate_quote(
                service_type=service_type,
                rim_count=rim_count,
                rim_size=rim_size,
                damage_description=damage_description,
                photos=photos,
            )

            # Persist quote if booking_id provided
            quote_id = None
            if booking_id:
                quote_id = save_quote(booking_id, quote)

            result = {**quote}
            if quote_id:
                result['quote_id'] = quote_id
            if booking_id:
                result['booking_id'] = booking_id

            return jsonify({'ok': True, 'data': result})

        except Exception:
            logger.exception("Error generating quote")
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # POST /api/damage/score — score damage from uploaded photo
    # ------------------------------------------------------------------
    @bp.route('/api/damage/score', methods=['POST'])
    @require_auth
    def score_damage_endpoint():
        try:
            body = request.get_json(silent=True) or {}

            image_data = body.get('image_data', '')
            media_type = body.get('media_type', 'image/jpeg')

            if not image_data:
                return jsonify({'ok': False, 'error': 'image_data is required (base64)'}), 400

            from damage_scorer import score_damage

            result = score_damage(image_data, media_type=media_type)

            if result is None:
                return jsonify({
                    'ok': False,
                    'error': 'Could not score damage. Check image quality or API key.'
                }), 422

            return jsonify({'ok': True, 'data': result})

        except Exception:
            logger.exception("Error scoring damage")
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # GET /api/quotes/<booking_id> — get quote for a booking
    # ------------------------------------------------------------------
    @bp.route('/api/quotes/<booking_id>', methods=['GET'])
    @require_auth
    def get_quote_endpoint(booking_id):
        try:
            from quoting_engine import get_quote_for_booking

            quote = get_quote_for_booking(booking_id)

            if quote is None:
                return jsonify({'ok': False, 'error': 'No quote found for this booking'}), 404

            return jsonify({'ok': True, 'data': quote})

        except Exception:
            logger.exception("Error fetching quote for booking %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# Self-registration — executed when the module is imported by admin_pro/__init__.py
# ---------------------------------------------------------------------------
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
