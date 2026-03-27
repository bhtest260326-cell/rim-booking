import os
import re
import json
import logging
import anthropic
from datetime import datetime

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

_INTENT_PROMPT = """You are a classifier for a mobile rim repair business inbox in Perth, Western Australia.

Determine whether the following email is a booking request or service enquiry for rim repair, wheel repair, or paint touch-up.

Reply with exactly one word: YES if it is a booking/service enquiry, NO if it is not (e.g. newsletters, wrong number, spam, general questions unrelated to booking a service, supplier emails, review requests from other businesses, etc).

Subject: {subject}
---
{body}
---

Reply YES or NO only."""


def is_booking_request(body, subject=""):
    """Return True if the email appears to be a rim repair booking or service enquiry."""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": _INTENT_PROMPT.format(
                subject=subject or "(no subject)",
                body=body[:2000]  # cap to keep token cost minimal
            )}]
        )
        answer = response.content[0].text.strip().upper()
        logger.info(f"Booking intent classification: {answer!r} (subject: {subject!r})")
        return answer == "YES" or answer.startswith("YES\n") or answer.startswith("YES ")
    except Exception as e:
        logger.error(f"Intent classification error: {e} — defaulting to process")
        return True  # fail open: if classifier errors, treat as booking


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
  "vehicle_year": "string or null",
  "vehicle_model": "string or null",
  "vehicle_colour": "string or null",
  "damage_description": "string or null",
  "service_type": "rim_repair | paint_touchup | multiple_rims | unknown",
  "num_rims": "integer or null",
  "preferred_date": "YYYY-MM-DD or null",
  "alternative_dates": ["YYYY-MM-DD", ...] or [],
  "preferred_time": "HH:MM or null",
  "address": "string or null",
  "suburb": "string or null",
  "notes": "string or null",
  "missing_fields": ["human-readable list of missing required fields using plain English only - e.g. 'your full name', 'your suburb', 'your preferred date', 'a description of the damage'. Never use code variable names."],
  "confidence": "high | medium | low"
}}

Required fields are: customer_name, customer_phone, suburb (or address), preferred_date, vehicle_make, vehicle_year, vehicle_model, damage_description.
vehicle_colour is NOT required — never ask for it.
customer_email is taken from the email headers automatically — never ask for it.

For address and suburb:
- If a full street address is provided, use it in the address field AND extract the suburb component into the suburb field
- If a postcode is provided, infer the suburb from it (e.g. 6008 = Subiaco, 6150 = Willetton, 6107 = Cannington, 6000 = Perth CBD, 6005 = West Perth, 6009 = Nedlands, 6010 = Claremont, 6018 = Innaloo, 6020 = Scarborough, 6021 = Stirling, 6023 = Duncraig, 6025 = Greenwood, 6027 = Joondalup, 6065 = Wanneroo, 6100 = Burswood, 6101 = Belmont, 6102 = Rivervale, 6103 = Kewdale, 6104 = Cloverdale, 6108 = Queens Park, 6110 = Armadale, 6112 = Armadale, 6147 = Lynwood, 6148 = Rossmoyne, 6149 = Shelley, 6151 = Como, 6152 = Applecross, 6153 = Ardross, 6155 = Canning Vale, 6156 = Fremantle, 6163 = South Fremantle, 6164 = Success, 6169 = Rockingham) and populate the suburb field
- If only a suburb name is given with no street, put it in suburb field
- Never ask for suburb if a street address or postcode was already provided

For damage_description:
- Extract any description of the type or nature of damage (e.g. "kerb rash", "scraped", "cracked rim", "buckled", "paint peeling", "scuffed alloy")
- If the customer describes the damage anywhere in their message, capture it here
- This is required — if not provided, include 'a description of the damage or type of repair needed' in missing_fields

For vehicle_year:
- Extract the year of the vehicle if mentioned (e.g. "2019 BMW", "my 2021 Hilux")
- Required — if not provided, include 'the year of your vehicle' in missing_fields

For preferred_date and alternative_dates:
- Today is {today}. Work out exact calendar dates from that anchor — do not guess or round.
- "Tuesday" or "next Tuesday" means the very next Tuesday after today. If today IS Tuesday, it means today. Never skip to the following week unless the customer says "the week after" or "in two weeks".
- When a customer names SPECIFIC days as options (e.g. "Tuesday or Wednesday", "Monday, Wednesday or Friday"), set preferred_date to the EARLIEST of those days (as actual YYYY-MM-DD dates) and put the remaining days in alternative_dates in order. ONLY include days the customer explicitly named — never add extra days they did not mention.
- Double-check your dates: if today is Friday 27 March 2026 and the customer says "Tuesday or Wednesday", the answer is preferred_date=2026-03-31, alternative_dates=["2026-04-01"]. Not April 2. Not any other day.
- If they give a range like "anytime next week" or "any day next week", set preferred_date to the first weekday of that range and leave alternative_dates empty
- Never pick a day of the week that the customer did not explicitly mention or imply
- If they say "morning" use 09:00, "afternoon" use 13:00, "end of day" use 16:00
- If they give a time window like "between 9am and 5pm", use 09:00 as preferred_time and note the window in notes
- Only mark preferred_date as missing if NO date or timeframe is mentioned at all

Return ONLY the JSON object, no other text."""

CORRECTION_PROMPT = """You are a booking assistant for a mobile rim repair business in Perth, Western Australia.

The business owner has sent an instruction about a pending booking. Today's date is {today}.

Current booking data:
{booking_json}

Owner's instruction:
"{correction_text}"

Interpret the instruction and update the booking accordingly. Examples:
- "Find a free 2 hour slot on 01/04" means set preferred_date to the next 01/04, preferred_time to 09:00, and add a note about 2 hour duration
- "change time to 11am" means set preferred_time to 11:00
- "address is 22 Smith St Balcatta" means set address field
- "move to next Thursday" means calculate next Thursday from today and set preferred_date

{slot_hint}Return the COMPLETE updated booking JSON with the same field structure as the original.
Return ONLY the JSON object, no other text."""


def extract_booking_details(message_body, subject="", customer_email=""):
    try:
        today = datetime.now().strftime("%A %d %B %Y")
        full_message = message_body[:4000]  # cap to control token usage
        if subject:
            full_message = f"Subject: {subject}\n\n{full_message}"

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(today=today, message=full_message)}]
        )

        raw = response.content[0].text.strip()
        # Robust code-block stripping
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1] if len(parts) > 1 else raw
            raw = raw.lstrip('json').strip()
        raw = raw.strip('`').strip()

        booking_data = json.loads(raw)

        # Validate and normalise extracted fields
        # missing_fields must be a list
        missing_fields = booking_data.pop('missing_fields', [])
        if not isinstance(missing_fields, list):
            missing_fields = [str(missing_fields)] if missing_fields else []

        # service_type must be one of the allowed values
        _allowed_services = {'rim_repair', 'paint_touchup', 'multiple_rims', 'unknown'}
        if booking_data.get('service_type') not in _allowed_services:
            logger.warning(f"Invalid service_type '{booking_data.get('service_type')}' — resetting to unknown")
            booking_data['service_type'] = 'unknown'

        # preferred_date must be YYYY-MM-DD
        for _df in ('preferred_date',):
            val = booking_data.get(_df)
            if val:
                try:
                    datetime.strptime(val, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid {_df} format '{val}' — clearing")
                    booking_data[_df] = None

        # alternative_dates must be a list of valid YYYY-MM-DD strings
        alt = booking_data.get('alternative_dates')
        if not isinstance(alt, list):
            booking_data['alternative_dates'] = []
        else:
            clean_alt = []
            for d in alt:
                try:
                    datetime.strptime(d, '%Y-%m-%d')
                    clean_alt.append(d)
                except (ValueError, TypeError):
                    pass
            booking_data['alternative_dates'] = clean_alt

        # preferred_time must be HH:MM
        pt = booking_data.get('preferred_time')
        if pt and not re.match(r'^\d{2}:\d{2}$', pt):
            logger.warning(f"Invalid preferred_time '{pt}' — clearing")
            booking_data['preferred_time'] = None

        # customer_phone must contain digits
        phone = booking_data.get('customer_phone')
        if phone and not re.search(r'\d', str(phone)):
            logger.warning(f"customer_phone has no digits '{phone}' — clearing")
            booking_data['customer_phone'] = None

        # num_rims must be an integer
        nr = booking_data.get('num_rims')
        if nr is not None:
            try:
                booking_data['num_rims'] = int(nr)
            except (ValueError, TypeError):
                logger.warning(f"Invalid num_rims '{nr}' — clearing")
                booking_data['num_rims'] = None

        # address/suburb — if both null, ensure missing_fields includes suburb
        if not booking_data.get('address') and not booking_data.get('suburb'):
            if not any('address' in f.lower() or 'suburb' in f.lower() or 'location' in f.lower() for f in missing_fields):
                missing_fields.append('your suburb or service address')

        # vehicle_make, vehicle_year, vehicle_model — required fields
        if not booking_data.get('vehicle_make'):
            if not any('make' in f.lower() or 'vehicle make' in f.lower() for f in missing_fields):
                missing_fields.append('the make of your vehicle (e.g. Toyota, BMW)')
        if not booking_data.get('vehicle_year'):
            if not any('year' in f.lower() for f in missing_fields):
                missing_fields.append('the year of your vehicle')
        if not booking_data.get('vehicle_model'):
            if not any('model' in f.lower() for f in missing_fields):
                missing_fields.append('the model of your vehicle (e.g. Camry, 3 Series)')

        # damage_description — required
        if not booking_data.get('damage_description'):
            if not any('damage' in f.lower() or 'repair' in f.lower() for f in missing_fields):
                missing_fields.append('a description of the damage or type of repair needed')

        if customer_email:
            booking_data['customer_email'] = customer_email

        needs_clarification = len(missing_fields) > 0
        logger.info(f"Extracted booking: confidence={booking_data.get('confidence')}, missing={missing_fields}")
        return booking_data, missing_fields, needs_clarification

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in extraction: {e}")
        return {}, ["the details of your booking request — please resend with your name, address, preferred date, and service type"], True
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error during extraction: {e}", exc_info=True)
        return {}, ["there was a temporary system issue — please try again in a moment"], True
    except Exception as e:
        logger.error(f"AI extraction error: {e}", exc_info=True)
        return {}, ["the details of your booking request — please resend with your name, address, preferred date, and service type"], True


def parse_owner_correction(original_booking, correction_text, slot_hint=None):
    try:
        today = datetime.now().strftime("%A %d %B %Y")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": CORRECTION_PROMPT.format(
                today=today,
                booking_json=json.dumps(original_booking, indent=2),
                correction_text=correction_text,
                slot_hint=f"A suggested available slot is {slot_hint}. " if slot_hint else ""
            )}]
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
        booking_data.get('vehicle_year'),
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
    damage = booking_data.get('damage_description')
    notes = booking_data.get('notes')

    msg = f"""NEW BOOKING REQUEST
Name: {name}
Contact: {phone}
Vehicle: {vehicle}
Service: {service}
Date: {date} at {time}
Address: {address}"""

    if damage:
        msg += f"\nDamage: {damage}"
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
