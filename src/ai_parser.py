import os
import json
import logging
import anthropic
from datetime import datetime

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

EXTRACTION_PROMPT = """You are a booking assistant for a mobile rim repair business in Perth, Western Australia.

Extract booking details from the following customer message. Today's date is {today}.

Customer message:
---
{message}
---

Return ONLY a JSON object with this exact structure:
{{
  "customer_name": "string or null",
  "customer_phone": "string or null",
  "vehicle_make": "string or null",
  "vehicle_model": "string or null",
  "vehicle_colour": "string or null",
  "service_type": "rim_repair | paint_touchup | multiple_rims | unknown",
  "num_rims": "integer or null",
  "preferred_date": "YYYY-MM-DD or null",
  "preferred_time": "HH:MM or null",
  "address": "string or null",
  "suburb": "string or null",
  "notes": "string or null",
  "missing_fields": ["human-readable list of missing required fields using plain English only - e.g. 'your full name', 'your service address', 'your preferred date', 'the type of service required'. Never use code variable names."],
  "confidence": "high | medium | low"
}}

Required fields are: customer_name, address (or suburb), preferred_date, service_type.
customer_phone is required if no email is available.

For preferred_date:
- Interpret relative dates like "tomorrow", "next Tuesday" based on today's date
- Vague availability MUST always resolve to a concrete date — NEVER add preferred_date to missing_fields when any timeframe hint is present. Examples:
  * "anytime next week" / "any day next week" → first Monday of next week at 09:00
  * "flexible" / "whenever suits" / "no preference" / "as soon as possible" → next available Monday at 09:00
  * "sometime this week" → next available weekday this week at 09:00
  * "next fortnight" → Monday in two weeks at 09:00
- If they say "morning" use 09:00, "afternoon" use 13:00, "end of day" use 16:00
- If they give a time window like "between 9am and 5pm", use 09:00 as preferred_time and note the window in notes
- Only mark preferred_date as missing if NO date, week, or timeframe whatsoever is mentioned

Return ONLY the JSON object, no other text."""

CORRECTION_PROMPT = """You are a booking assistant for a mobile rim repair business in Perth, Western Australia.

The business owner has sent an instruction about a pending booking. Today's date is {today}.

Current booking data:
{booking_json}

Owner's instruction:
"{correction_text}"
{slot_hint}
Interpret the instruction and update the booking accordingly. Examples:
- "Find a free 2 hour slot on 01/04" means set preferred_date to the next 01/04 and preferred_time to the next available slot (use the slot hint above if provided)
- "change time to 11am" means set preferred_time to 11:00
- "address is 22 Smith St Balcatta" means set address field
- "move to next Thursday" means calculate next Thursday from today and set preferred_date

Return the COMPLETE updated booking JSON with the same field structure as the original.
Return ONLY the JSON object, no other text."""


def extract_booking_details(message_body, subject="", customer_email=""):
    try:
        today = datetime.now().strftime("%A %d %B %Y")
        full_message = message_body
        if subject:
            full_message = f"Subject: {subject}\n\n{message_body}"

        prompt = (EXTRACTION_PROMPT
                  .replace('{today}', today)
                  .replace('{message}', full_message)
                  .replace('{{', '{')
                  .replace('}}', '}'))
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]

        booking_data = json.loads(raw.strip())
        missing_fields = booking_data.pop('missing_fields', [])

        if customer_email:
            booking_data['customer_email'] = customer_email

        needs_clarification = len(missing_fields) > 0
        logger.info(f"Extracted booking: confidence={booking_data.get('confidence')}, missing={missing_fields}")
        return booking_data, missing_fields, needs_clarification

    except json.JSONDecodeError as e:
        logger.error(f"AI_PARSE_FAIL json_decode: {e}")
        return {}, ["the details of your booking request — please resend with your name, address, preferred date, and service type"], True
    except Exception as e:
        logger.error(f"AI_PARSE_FAIL {type(e).__name__}: {e}", exc_info=True)
        return {}, ["the details of your booking request — please resend with your name, address, preferred date, and service type"], True


def parse_owner_correction(original_booking, correction_text, slot_hint=None):
    try:
        today = datetime.now().strftime("%A %d %B %Y")
        hint_text = (
            f"\nAvailable slot (accounting for travel time between jobs): {slot_hint}\n"
            f"Use this date and time when the owner asks to find a free slot.\n"
            if slot_hint else ""
        )
        prompt = (CORRECTION_PROMPT
                  .replace('{today}', today)
                  .replace('{booking_json}', json.dumps(original_booking, indent=2))
                  .replace('{correction_text}', correction_text)
                  .replace('{slot_hint}', hint_text))
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]

        updated = json.loads(raw.strip())
        logger.info(f"Booking updated via correction: {correction_text}")
        return updated

    except Exception as e:
        logger.error(f"Correction parse error: {e}")
        return original_booking


def format_booking_for_owner(booking_data):
    name = booking_data.get('customer_name') or 'Unknown'
    phone = booking_data.get('customer_phone') or booking_data.get('customer_email') or 'N/A'
    vehicle = ' '.join(filter(None, [
        booking_data.get('vehicle_colour'),
        booking_data.get('vehicle_make'),
        booking_data.get('vehicle_model')
    ])) or 'Unknown vehicle'

    service = booking_data.get('service_type', 'unknown').replace('_', ' ').title()
    num_rims = booking_data.get('num_rims')
    if num_rims:
        service += f" x{num_rims}"

    date = booking_data.get('preferred_date') or 'TBC'
    time = booking_data.get('preferred_time') or 'TBC'
    address = booking_data.get('address') or booking_data.get('suburb') or 'TBC'
    notes = booking_data.get('notes')

    msg = f"""NEW BOOKING REQUEST
Name: {name}
Contact: {phone}
Vehicle: {vehicle}
Service: {service}
Date: {date} at {time}
Address: {address}"""

    if notes:
        msg += f"\nNotes: {notes}"

    msg += "\n\nReply YES to confirm, NO to decline, or send any changes (e.g. 'find a free slot on 01/04', 'change time to 11am')"
    return msg


def merge_booking_data(original, new_data):
    """
    Merge two booking data dicts.
    Original values are kept. New values only fill in null/missing fields.
    """
    merged = dict(original)
    for key, value in new_data.items():
        if value is not None and value != '' and value != 'unknown':
            if not merged.get(key):
                merged[key] = value
    return merged
