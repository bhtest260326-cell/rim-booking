"""
quoting_engine.py — AI-powered quoting system for rim repair bookings.

Generates price estimates based on service type, rim count, rim size,
damage description, and optional photo analysis via Claude Vision.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Price matrix (base prices in AUD, configurable via env)
# ---------------------------------------------------------------------------

DEFAULT_PRICE_MATRIX = {
    "standard": {"low": 80, "high": 120, "label": "Standard rim repair"},
    "diamond_cut": {"low": 120, "high": 180, "label": "Diamond cut repair"},
    "custom_paint": {"low": 150, "high": 250, "label": "Custom paint/respray"},
    "gutter_rash": {"low": 60, "high": 90, "label": "Gutter rash repair"},
    "crack_repair": {"low": 100, "high": 160, "label": "Crack repair"},
}

# Aliases: map common service_type values to matrix keys
SERVICE_ALIASES = {
    "standard": "standard",
    "standard rim repair": "standard",
    "rim repair": "standard",
    "diamond cut": "diamond_cut",
    "diamond_cut": "diamond_cut",
    "diamond cut repair": "diamond_cut",
    "custom paint": "custom_paint",
    "custom_paint": "custom_paint",
    "respray": "custom_paint",
    "paint": "custom_paint",
    "gutter rash": "gutter_rash",
    "gutter_rash": "gutter_rash",
    "kerb rash": "gutter_rash",
    "curb rash": "gutter_rash",
    "crack": "crack_repair",
    "crack_repair": "crack_repair",
    "crack repair": "crack_repair",
}


def _load_price_matrix() -> dict:
    """Load price matrix, allowing env-var override via PRICE_MATRIX_JSON."""
    override = os.environ.get("PRICE_MATRIX_JSON", "")
    if override:
        try:
            return json.loads(override)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid PRICE_MATRIX_JSON env var, using defaults")
    return DEFAULT_PRICE_MATRIX


def _resolve_service(service_type: str) -> str | None:
    """Resolve a user-supplied service type string to a matrix key."""
    if not service_type:
        return None
    key = service_type.strip().lower()
    return SERVICE_ALIASES.get(key)


def _size_multiplier(rim_size: int | float | None) -> float:
    """Return price multiplier based on rim diameter (inches)."""
    if rim_size and rim_size > 18:
        return 1.20  # +20% for large rims
    return 1.0


def _count_discount(rim_count: int) -> float:
    """Return discount multiplier for bulk rim orders."""
    if rim_count >= 4:
        return 0.90  # -10% discount
    return 1.0


def _severity_multiplier(severity: int | None) -> float:
    """Map a 1-10 severity score to a price multiplier."""
    if severity is None:
        return 1.0
    if severity <= 3:
        return 0.85   # cosmetic — below base
    if severity <= 6:
        return 1.0    # moderate — base price
    if severity <= 9:
        return 1.25   # significant — above base
    return 1.50       # structural — well above base


def generate_quote(
    service_type: str,
    rim_count: int = 1,
    rim_size: int | float | None = None,
    damage_description: str = "",
    photos: list | None = None,
    severity_score: int | None = None,
) -> dict:
    """Generate a price quote for a rim repair job.

    Args:
        service_type: e.g. "gutter_rash", "diamond cut", "crack repair"
        rim_count: number of rims to repair (default 1)
        rim_size: rim diameter in inches (optional)
        damage_description: free-text damage description (optional)
        photos: list of image dicts for Claude Vision analysis (optional)
        severity_score: pre-computed 1-10 severity (optional; if photos
                        provided and no severity_score, will auto-score)

    Returns:
        dict with keys: estimate_low, estimate_high, confidence, breakdown,
              service_key, adjustments
    """
    matrix = _load_price_matrix()
    rim_count = max(1, int(rim_count or 1))

    service_key = _resolve_service(service_type)
    if not service_key or service_key not in matrix:
        # Fallback: use standard if unrecognised
        logger.info("Unrecognised service '%s', falling back to standard", service_type)
        service_key = "standard"

    entry = matrix[service_key]
    base_low = entry["low"]
    base_high = entry["high"]

    # --- Photo-based severity scoring ---
    if photos and severity_score is None:
        try:
            from damage_scorer import score_damage_from_images
            result = score_damage_from_images(photos)
            if result:
                severity_score = result.get("severity")
        except Exception:
            logger.exception("Photo scoring failed during quote generation")

    # --- Multipliers ---
    size_mult = _size_multiplier(rim_size)
    count_disc = _count_discount(rim_count)
    sev_mult = _severity_multiplier(severity_score)

    # --- Calculate ---
    per_rim_low = base_low * size_mult * sev_mult
    per_rim_high = base_high * size_mult * sev_mult

    total_low = per_rim_low * rim_count * count_disc
    total_high = per_rim_high * rim_count * count_disc

    # Round to nearest dollar
    total_low = round(total_low)
    total_high = round(total_high)

    # --- Confidence ---
    confidence = 0.7  # base confidence
    if severity_score is not None:
        confidence += 0.15  # photo-based assessment boosts confidence
    if damage_description and len(damage_description) > 20:
        confidence += 0.05
    if rim_size:
        confidence += 0.05
    confidence = min(confidence, 1.0)
    confidence = round(confidence, 2)

    # --- Breakdown ---
    adjustments = []
    breakdown = [
        {
            "item": entry.get("label", service_key),
            "per_rim_low": base_low,
            "per_rim_high": base_high,
            "quantity": rim_count,
        }
    ]

    if size_mult != 1.0:
        adjustments.append(f"Large rim ({rim_size}\") surcharge: +20%")
    if count_disc != 1.0:
        adjustments.append(f"Bulk discount ({rim_count} rims): -10%")
    if sev_mult != 1.0:
        adj_pct = round((sev_mult - 1.0) * 100)
        direction = "+" if adj_pct > 0 else ""
        adjustments.append(f"Severity adjustment (score {severity_score}): {direction}{adj_pct}%")

    return {
        "estimate_low": total_low,
        "estimate_high": total_high,
        "confidence": confidence,
        "breakdown": breakdown,
        "service_key": service_key,
        "adjustments": adjustments,
        "rim_count": rim_count,
        "rim_size": rim_size,
        "severity_score": severity_score,
    }


# ---------------------------------------------------------------------------
# DB persistence (quotes table)
# ---------------------------------------------------------------------------

def _ensure_quotes_table():
    """Create the quotes table if it does not exist."""
    from state_manager import _get_conn
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quotes (
                id              TEXT PRIMARY KEY,
                booking_id      TEXT,
                estimate_low    INTEGER NOT NULL,
                estimate_high   INTEGER NOT NULL,
                confidence      REAL NOT NULL,
                breakdown_json  TEXT NOT NULL,
                service_key     TEXT,
                rim_count       INTEGER,
                rim_size        REAL,
                severity_score  INTEGER,
                adjustments_json TEXT,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_quotes_booking ON quotes(booking_id)"
        )


def save_quote(booking_id: str | None, quote: dict) -> str:
    """Persist a quote to the database. Returns the quote id."""
    import uuid
    from state_manager import _get_conn

    _ensure_quotes_table()

    quote_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO quotes
               (id, booking_id, estimate_low, estimate_high, confidence,
                breakdown_json, service_key, rim_count, rim_size,
                severity_score, adjustments_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                quote_id,
                booking_id,
                quote["estimate_low"],
                quote["estimate_high"],
                quote["confidence"],
                json.dumps(quote.get("breakdown", [])),
                quote.get("service_key"),
                quote.get("rim_count"),
                quote.get("rim_size"),
                quote.get("severity_score"),
                json.dumps(quote.get("adjustments", [])),
                now,
            ),
        )

    logger.info("Saved quote %s for booking %s: $%d-$%d",
                quote_id, booking_id, quote["estimate_low"], quote["estimate_high"])
    return quote_id


def get_quote_for_booking(booking_id: str) -> dict | None:
    """Retrieve the most recent quote for a booking."""
    from state_manager import _get_conn

    _ensure_quotes_table()

    with _get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM quotes
               WHERE booking_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (booking_id,),
        ).fetchone()

    if not row:
        return None

    d = dict(row)
    try:
        d["breakdown"] = json.loads(d.pop("breakdown_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["breakdown"] = []
    try:
        d["adjustments"] = json.loads(d.pop("adjustments_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["adjustments"] = []
    return d
