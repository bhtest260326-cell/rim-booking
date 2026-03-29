"""
admin_pro/api/competitors.py
Competitor price monitoring API endpoints.
"""

import logging
from flask import request, jsonify
from state_manager import StateManager

logger = logging.getLogger(__name__)

_sm = StateManager()


def register(bp, require_auth):

    # ------------------------------------------------------------------
    # GET /api/competitors — list all competitors
    # ------------------------------------------------------------------
    @bp.route("/api/competitors", methods=["GET"])
    @require_auth
    def list_competitors():
        try:
            active_only = request.args.get('active_only', '1') == '1'
            competitors = _sm.get_competitors(active_only=active_only)
            return jsonify({'ok': True, 'data': competitors})
        except Exception as e:
            logger.error("list_competitors error: %s", e, exc_info=True)
            return jsonify({'ok': False, 'error': str(e)}), 500

    # ------------------------------------------------------------------
    # POST /api/competitors — add a competitor
    # ------------------------------------------------------------------
    @bp.route("/api/competitors", methods=["POST"])
    @require_auth
    def add_competitor():
        try:
            body = request.get_json(force=True) or {}
            name = (body.get('name') or '').strip()
            if not name:
                return jsonify({'ok': False, 'error': 'name is required'}), 400
            cid = _sm.add_competitor(
                name=name,
                website=body.get('website'),
                phone=body.get('phone'),
                location=body.get('location'),
            )
            return jsonify({'ok': True, 'data': {'id': cid}})
        except Exception as e:
            logger.error("add_competitor error: %s", e, exc_info=True)
            return jsonify({'ok': False, 'error': str(e)}), 500

    # ------------------------------------------------------------------
    # PUT /api/competitors/<id> — update a competitor
    # ------------------------------------------------------------------
    @bp.route("/api/competitors/<int:comp_id>", methods=["PUT"])
    @require_auth
    def update_competitor(comp_id):
        try:
            body = request.get_json(force=True) or {}
            updated = _sm.update_competitor(comp_id, **body)
            if not updated:
                return jsonify({'ok': False, 'error': 'Not found or no valid fields'}), 404
            return jsonify({'ok': True})
        except Exception as e:
            logger.error("update_competitor error: %s", e, exc_info=True)
            return jsonify({'ok': False, 'error': str(e)}), 500

    # ------------------------------------------------------------------
    # GET /api/competitors/prices — all price data
    # ------------------------------------------------------------------
    @bp.route("/api/competitors/prices", methods=["GET"])
    @require_auth
    def get_prices():
        try:
            service_type = request.args.get('service_type')
            competitor_id = request.args.get('competitor_id', type=int)
            prices = _sm.get_competitor_prices(
                service_type=service_type,
                competitor_id=competitor_id,
            )
            return jsonify({'ok': True, 'data': prices})
        except Exception as e:
            logger.error("get_prices error: %s", e, exc_info=True)
            return jsonify({'ok': False, 'error': str(e)}), 500

    # ------------------------------------------------------------------
    # POST /api/competitors/<id>/prices — add price observation
    # ------------------------------------------------------------------
    @bp.route("/api/competitors/<int:comp_id>/prices", methods=["POST"])
    @require_auth
    def add_price(comp_id):
        try:
            body = request.get_json(force=True) or {}
            service_type = (body.get('service_type') or '').strip()
            if not service_type:
                return jsonify({'ok': False, 'error': 'service_type is required'}), 400
            price_low = body.get('price_low')
            price_high = body.get('price_high')
            if price_low is None and price_high is None:
                return jsonify({'ok': False, 'error': 'at least one of price_low or price_high is required'}), 400
            pid = _sm.add_competitor_price(
                competitor_id=comp_id,
                service_type=service_type,
                price_low=price_low,
                price_high=price_high,
                source=body.get('source'),
                notes=body.get('notes'),
            )
            return jsonify({'ok': True, 'data': {'id': pid}})
        except Exception as e:
            logger.error("add_price error: %s", e, exc_info=True)
            return jsonify({'ok': False, 'error': str(e)}), 500

    # ------------------------------------------------------------------
    # GET /api/competitors/comparison — price comparison summary
    # ------------------------------------------------------------------
    @bp.route("/api/competitors/comparison", methods=["GET"])
    @require_auth
    def price_comparison():
        try:
            service_type = request.args.get('service_type')
            comparison = _sm.get_price_comparison(service_type=service_type)
            return jsonify({'ok': True, 'data': comparison})
        except Exception as e:
            logger.error("price_comparison error: %s", e, exc_info=True)
            return jsonify({'ok': False, 'error': str(e)}), 500


# Auto-register when imported by admin_pro/__init__.py
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
