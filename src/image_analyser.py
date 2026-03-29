"""
image_analyser.py — AI-powered rim damage assessment using Claude vision.

Accepts one or more base64-encoded images and returns a structured
assessment: damage level, rims detected, estimated job duration, price range.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')

_SYSTEM_PROMPT = (
    "You are an expert wheel and rim repair technician assessor for Wheel Doctor, "
    "a mobile rim repair service in Perth, Western Australia.\n\n"
    "Analyse customer-submitted photos of damaged rims and provide:\n"
    "1. Damage severity (minor scuff/scratch, moderate kerb damage, or severe buckle/crack)\n"
    "2. Number of rims visible that need repair\n"
    "3. Estimated job duration in minutes\n"
    "4. Price estimate in AUD\n\n"
    "Pricing guide:\n"
    "  Minor scuff/scratch — 1 rim: $120–$150, 90–120 min\n"
    "  Moderate kerb damage — 1 rim: $150–$200, 120–150 min\n"
    "  Severe buckle/crack  — 1 rim: $200–$280, 150–180 min\n"
    "  Each additional rim: +$100–$150, +60–90 min\n\n"
    "Respond ONLY with valid JSON — no markdown, no prose."
)

_ANALYSIS_PROMPT = (
    "Analyse the rim damage shown. "
    "Respond with this exact JSON structure:\n"
    "{\n"
    '  "damage_level": "minor|moderate|severe|not_visible",\n'
    '  "num_rims_detected": 1,\n'
    '  "estimated_minutes": 120,\n'
    '  "price_min": 120,\n'
    '  "price_max": 150,\n'
    '  "assessment_notes": "Brief professional description of the damage visible",\n'
    '  "confidence": "high|medium|low"\n'
    "}\n\n"
    "If no rims are clearly visible or the image quality is too poor to assess, "
    'set damage_level to "not_visible" and confidence to "low".'
)

_REQUIRED_KEYS = {
    'damage_level', 'num_rims_detected', 'estimated_minutes',
    'price_min', 'price_max', 'assessment_notes', 'confidence',
}


def analyse_rim_images(images: list) -> dict | None:
    """Analyse rim damage from one or more images using Claude vision.

    Args:
        images: list of dicts, each with:
            - 'data':       base64-encoded image bytes (no data-URI prefix)
            - 'media_type': MIME type string, e.g. 'image/jpeg'

    Returns:
        dict with keys: damage_level, num_rims_detected, estimated_minutes,
        price_min, price_max, assessment_notes, confidence
        — or None on failure / missing API key.
    """
    if not images:
        return None

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping image analysis")
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=30)

        content = []
        for img in images[:4]:  # cap at 4 images to control cost/latency
            media_type = img.get('media_type', 'image/jpeg')
            # Normalise media type — Claude only accepts jpeg/png/gif/webp
            if media_type not in ('image/jpeg', 'image/png', 'image/gif', 'image/webp'):
                media_type = 'image/jpeg'
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": img['data'],
                }
            })
        content.append({"type": "text", "text": _ANALYSIS_PROMPT})

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}]
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if the model wraps its response
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)

        if not _REQUIRED_KEYS.issubset(result.keys()):
            missing = _REQUIRED_KEYS - result.keys()
            logger.warning("Image analysis response missing keys: %s", missing)
            return None

        # Coerce numeric fields to int for safety
        for field in ('num_rims_detected', 'estimated_minutes', 'price_min', 'price_max'):
            try:
                result[field] = int(result[field])
            except (TypeError, ValueError):
                pass

        logger.info(
            "Image analysis: %s damage, %d rim(s), $%d–$%d, %d min [confidence=%s]",
            result['damage_level'], result['num_rims_detected'],
            result['price_min'], result['price_max'],
            result['estimated_minutes'], result['confidence'],
        )
        return result

    except Exception as e:
        logger.error("Image analysis failed: %s", e, exc_info=True)
        return None


def download_twilio_media(media_url: str, media_type: str = 'image/jpeg') -> dict | None:
    """Download a Twilio MMS media URL and return an image dict for analyse_rim_images.

    Twilio media URLs require HTTP Basic Auth (account SID + auth token).
    Returns {'data': base64str, 'media_type': str} or None on failure.
    """
    if not media_url.startswith('https://api.twilio.com/'):
        logger.warning("Rejecting non-Twilio media URL: %s", media_url)
        return None

    account_sid = os.environ.get('TWILIO_ACCOUNT_SID', '')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '')
    if not account_sid or not auth_token:
        logger.warning("Twilio credentials not set — cannot download MMS media")
        return None

    try:
        import urllib.request
        import base64 as _b64

        credentials = f"{account_sid}:{auth_token}"
        encoded = _b64.b64encode(credentials.encode()).decode()

        req = urllib.request.Request(media_url)
        req.add_header('Authorization', f'Basic {encoded}')

        with urllib.request.urlopen(req, timeout=10) as resp:
            image_bytes = resp.read()

        return {
            'data': _b64.b64encode(image_bytes).decode(),
            'media_type': media_type,
        }
    except Exception as e:
        logger.error("Failed to download Twilio media %s: %s", media_url, e)
        return None
