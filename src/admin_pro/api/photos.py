"""
admin_pro/api/photos.py — Before/after photo upload and retrieval endpoints.
"""

import os
import logging

from flask import request, jsonify, send_from_directory

from state_manager import StateManager

logger = logging.getLogger(__name__)

ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/webp'}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB

# Base directory for photo storage — lives next to the SQLite DB
_DATA_DIR = os.environ.get('DATA_DIR', '/data')
PHOTOS_DIR = os.path.join(_DATA_DIR, 'photos')


def _photos_dir_for(booking_id: str) -> str:
    """Return (and create) the per-booking photo directory."""
    d = os.path.join(PHOTOS_DIR, booking_id)
    os.makedirs(d, exist_ok=True)
    return d


def register(bp, require_auth):

    # ------------------------------------------------------------------
    # POST /api/bookings/<id>/photos  — upload a photo
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/photos', methods=['POST'])
    @require_auth
    def upload_photo(booking_id):
        if 'file' not in request.files:
            return jsonify({'ok': False, 'error': 'No file provided'}), 400

        f = request.files['file']
        if not f or not f.filename:
            return jsonify({'ok': False, 'error': 'Empty file'}), 400

        mime = f.content_type or ''
        if mime not in ALLOWED_MIME:
            return jsonify({'ok': False, 'error': f'Unsupported file type: {mime}. Allowed: JPEG, PNG, WebP'}), 400

        photo_type = request.form.get('photo_type', 'before')
        if photo_type not in ('before', 'after'):
            return jsonify({'ok': False, 'error': 'photo_type must be "before" or "after"'}), 400

        notes = request.form.get('notes', '').strip() or None

        # Read file content and check size
        data = f.read()
        if len(data) > MAX_SIZE:
            return jsonify({'ok': False, 'error': 'File exceeds 10 MB limit'}), 400

        # Sanitise filename: keep extension, prefix with type + timestamp
        from datetime import datetime, timezone
        import re
        ext = os.path.splitext(f.filename)[1].lower() or '.jpg'
        safe_ext = ext if ext in ('.jpg', '.jpeg', '.png', '.webp') else '.jpg'
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        safe_name = f'{photo_type}_{ts}{safe_ext}'

        dest_dir = _photos_dir_for(booking_id)
        dest_path = os.path.join(dest_dir, safe_name)
        with open(dest_path, 'wb') as out:
            out.write(data)

        sm = StateManager()
        photo_id = sm.add_booking_photo(
            booking_id=booking_id,
            photo_type=photo_type,
            filename=safe_name,
            mime_type=mime,
            file_size=len(data),
            storage_path=dest_path,
            notes=notes,
            uploaded_by='admin',
        )
        logger.info('Photo %d uploaded for booking %s (%s, %d bytes)',
                     photo_id, booking_id, photo_type, len(data))

        return jsonify({'ok': True, 'data': {'photo_id': photo_id, 'filename': safe_name}})

    # ------------------------------------------------------------------
    # GET /api/bookings/<id>/photos  — list photos
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/photos', methods=['GET'])
    @require_auth
    def list_photos(booking_id):
        sm = StateManager()
        photos = sm.get_booking_photos(booking_id)
        return jsonify({'ok': True, 'data': {'photos': photos}})

    # ------------------------------------------------------------------
    # GET /api/photos/<photo_id>  — serve photo file
    # ------------------------------------------------------------------
    @bp.route('/api/photos/<int:photo_id>', methods=['GET'])
    @require_auth
    def serve_photo(photo_id):
        sm = StateManager()
        photo = sm.get_booking_photo(photo_id)
        if not photo:
            return jsonify({'ok': False, 'error': 'Photo not found'}), 404

        storage_path = photo.get('storage_path', '')
        if not storage_path or not os.path.isfile(storage_path):
            return jsonify({'ok': False, 'error': 'Photo file missing'}), 404

        directory = os.path.dirname(storage_path)
        filename = os.path.basename(storage_path)
        return send_from_directory(directory, filename, mimetype=photo.get('mime_type', 'image/jpeg'))

    # ------------------------------------------------------------------
    # DELETE /api/photos/<photo_id>  — delete photo
    # ------------------------------------------------------------------
    @bp.route('/api/photos/<int:photo_id>', methods=['DELETE'])
    @require_auth
    def delete_photo(photo_id):
        sm = StateManager()
        photo = sm.get_booking_photo(photo_id)
        if not photo:
            return jsonify({'ok': False, 'error': 'Photo not found'}), 404

        # Delete file from disk
        storage_path = photo.get('storage_path', '')
        if storage_path and os.path.isfile(storage_path):
            try:
                os.remove(storage_path)
            except OSError as e:
                logger.warning('Could not delete photo file %s: %s', storage_path, e)

        sm.delete_booking_photo(photo_id)
        logger.info('Photo %d deleted for booking %s', photo_id, photo['booking_id'])
        return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Self-registration — executed when the module is imported by admin_pro/__init__.py
# ---------------------------------------------------------------------------
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
