"""
damage_scorer.py — AI-powered damage severity scoring using Claude Vision.

Analyses rim damage photos and returns a structured severity assessment
with damage types, recommended service, and a 1-10 severity score.
"""

import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# In-memory cache keyed by image content hash
_score_cache: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Severity scale reference
# ---------------------------------------------------------------------------
# 1-3  : Cosmetic  — light scratches, minor scuffs
# 4-6  : Moderate  — noticeable kerb rash, paint loss, small dents
# 7-9  : Significant — deep gouges, visible cracks, bent lip
# 10   : Structural — cracked through, unsafe to drive

DAMAGE_TYPES = [
    "gutter_rash",
    "scratch",
    "scuff",
    "crack",
    "bent",
    "buckle",
    "paint_loss",
    "corrosion",
    "chip",
    "dent",
]

_SYSTEM_PROMPT = (
    "You are an expert wheel and rim repair technician for Wheel Doctor, "
    "a mobile rim repair service in Perth, Western Australia.\n\n"
    "You assess damage in customer-submitted photos and provide a structured "
    "severity score.\n\n"
    "Severity scale:\n"
    "  1-3: Cosmetic — light scratches, minor scuffs, barely noticeable\n"
    "  4-6: Moderate — noticeable kerb rash, paint loss, small dents\n"
    "  7-9: Significant — deep gouges, visible cracks, bent lip\n"
    "  10:  Structural — cracked through, unsafe to drive on\n\n"
    "Respond ONLY with valid JSON — no markdown, no prose."
)

_SCORING_PROMPT = (
    "Assess the rim damage in this image. "
    "Respond with this exact JSON structure:\n"
    "{\n"
    '  "severity": <integer 1-10>,\n'
    '  "damage_types": ["gutter_rash", "crack", ...],\n'
    '  "recommended_service": "standard|diamond_cut|custom_paint|gutter_rash|crack_repair",\n'
    '  "description": "Brief professional description of damage observed",\n'
    '  "confidence": "high|medium|low"\n'
    "}\n\n"
    "Valid damage_types: gutter_rash, scratch, scuff, crack, bent, buckle, "
    "paint_loss, corrosion, chip, dent.\n"
    "If the image does not show a rim or is too unclear, return severity 0 "
    'and confidence "low".'
)

_REQUIRED_KEYS = {"severity", "damage_types", "recommended_service", "description"}


def _image_hash(image_data: bytes | str) -> str:
    """Compute a short hash for cache keying."""
    if isinstance(image_data, str):
        image_data = image_data.encode("utf-8")
    return hashlib.sha256(image_data[:8192]).hexdigest()[:16]


def score_damage(image_data: str, media_type: str = "image/jpeg") -> dict | None:
    """Score damage from a single base64-encoded image.

    Args:
        image_data: base64-encoded image bytes (no data-URI prefix)
        media_type: MIME type, e.g. 'image/jpeg', 'image/png'

    Returns:
        dict with keys: severity (1-10), damage_types, recommended_service,
        description, confidence — or None on failure.
    """
    return score_damage_from_images([{"data": image_data, "media_type": media_type}])


def score_damage_from_images(images: list[dict]) -> dict | None:
    """Score damage from one or more images.

    Args:
        images: list of dicts with 'data' (base64) and 'media_type' keys.

    Returns:
        dict with severity assessment or None on failure.
    """
    if not images:
        return None

    # Check cache using first image hash
    cache_key = _image_hash(images[0].get("data", ""))
    if cache_key in _score_cache:
        logger.debug("Damage score cache hit: %s", cache_key)
        return _score_cache[cache_key]

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping damage scoring")
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=30)

        content = []
        for img in images[:4]:  # cap at 4 images
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/jpeg"),
                        "data": img["data"],
                    },
                }
            )
        content.append({"type": "text", "text": _SCORING_PROMPT})

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        raw_text = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        result = json.loads(raw_text)

        # Validate required keys
        missing = _REQUIRED_KEYS - set(result.keys())
        if missing:
            logger.warning("Damage scorer response missing keys: %s", missing)
            return None

        # Clamp severity to 0-10
        result["severity"] = max(0, min(10, int(result["severity"])))

        # Validate damage_types
        result["damage_types"] = [
            dt for dt in result.get("damage_types", []) if dt in DAMAGE_TYPES
        ]

        # Validate recommended_service
        valid_services = {
            "standard", "diamond_cut", "custom_paint", "gutter_rash", "crack_repair"
        }
        if result.get("recommended_service") not in valid_services:
            result["recommended_service"] = "standard"

        # Cache result
        _score_cache[cache_key] = result
        logger.info(
            "Damage scored: severity=%d, types=%s, service=%s",
            result["severity"],
            result["damage_types"],
            result["recommended_service"],
        )
        return result

    except json.JSONDecodeError:
        logger.warning("Damage scorer returned invalid JSON: %s", raw_text[:200])
        return None
    except Exception:
        logger.exception("Damage scoring failed")
        return None


def clear_cache():
    """Clear the in-memory score cache."""
    _score_cache.clear()
