import logging
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Label definitions with Gmail colour codes
# Gmail background/text colour pairs (from Gmail API colour palette)
LABELS = {
    'Rim Repairs/Pending Reply': {
        'color': {'backgroundColor': '#fb4c2f', 'textColor': '#ffffff'},  # Red - awaiting customer info
        'description': 'Customer contacted, awaiting more info from them'
    },
    'Rim Repairs/Awaiting Confirmation': {
        'color': {'backgroundColor': '#ffad47', 'textColor': '#ffffff'},  # Orange - sent to owner
        'description': 'Booking details extracted, awaiting owner YES/NO'
    },
    'Rim Repairs/Confirmed': {
        'color': {'backgroundColor': '#16a766', 'textColor': '#ffffff'},  # Green - confirmed
        'description': 'Booking confirmed, calendar event created'
    },
    'Rim Repairs/Declined': {
        'color': {'backgroundColor': '#8e63ce', 'textColor': '#ffffff'},  # Purple - declined
        'description': 'Booking declined by owner'
    },
    'Rim Repairs/Processed': {
        'color': {'backgroundColor': '#999999', 'textColor': '#ffffff'},  # Grey - catch-all processed
        'description': 'Email has been processed by the booking system'
    },
}

_label_cache = {}

def get_or_create_label(service, label_name):
    """Get or create a Gmail label by name, with colour. Returns label ID or None."""
    global _label_cache

    if label_name in _label_cache:
        return _label_cache[label_name]

    try:
        result = service.users().labels().list(userId='me').execute()
        existing = {l['name']: l['id'] for l in result.get('labels', [])}

        if label_name in existing:
            _label_cache[label_name] = existing[label_name]
            return existing[label_name]

        # Create with colour if defined
        body = {
            'name': label_name,
            'labelListVisibility': 'labelShow',
            'messageListVisibility': 'show',
        }

        if label_name in LABELS and 'color' in LABELS[label_name]:
            body['color'] = LABELS[label_name]['color']

        created = service.users().labels().create(userId='me', body=body).execute()
        label_id = created['id']
        _label_cache[label_name] = label_id
        logger.info(f"Created label: {label_name}")
        return label_id

    except HttpError as e:
        logger.error(f"Label create error for '{label_name}': {e}")
        return None
    except Exception as e:
        logger.error(f"Label error for '{label_name}': {e}")
        return None

def apply_label(service, msg_id, label_name, remove_labels=None):
    """Apply a label to a message, optionally removing others."""
    try:
        add_id = get_or_create_label(service, label_name)
        if not add_id:
            return

        remove_ids = []
        if remove_labels:
            for rl in remove_labels:
                rid = get_or_create_label(service, rl)
                if rid:
                    remove_ids.append(rid)

        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={
                'addLabelIds': [add_id],
                'removeLabelIds': remove_ids
            }
        ).execute()
        logger.info(f"Applied label '{label_name}' to message {msg_id}")

    except HttpError as e:
        logger.error(f"Apply label error: {e}")
    except Exception as e:
        logger.error(f"Apply label error: {e}")

def initialise_labels(service):
    """Pre-create all labels on startup so they appear in Gmail sidebar."""
    for label_name in LABELS:
        get_or_create_label(service, label_name)

def label_pending_reply(service, msg_id):
    """Red — we asked customer for more info, waiting on them."""
    apply_label(service, msg_id, 'Rim Repairs/Pending Reply',
                remove_labels=['Rim Repairs/Awaiting Confirmation', 'Rim Repairs/Confirmed', 'Rim Repairs/Declined', 'Rim Repairs/Processed'])

def label_awaiting_confirmation(service, msg_id):
    """Orange — booking extracted, sent to owner for YES/NO."""
    apply_label(service, msg_id, 'Rim Repairs/Awaiting Confirmation',
                remove_labels=['Rim Repairs/Pending Reply', 'Rim Repairs/Confirmed', 'Rim Repairs/Declined', 'Rim Repairs/Processed'])

def label_confirmed(service, msg_id):
    """Green — owner confirmed, calendar event created. Archived out of inbox."""
    apply_label(service, msg_id, 'Rim Repairs/Confirmed',
                remove_labels=['Rim Repairs/Pending Reply', 'Rim Repairs/Awaiting Confirmation', 'Rim Repairs/Declined', 'Rim Repairs/Processed'])
    # Archive — remove from inbox so it sits in the Confirmed label folder
    try:
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['INBOX']}
        ).execute()
        logger.info(f"Archived message {msg_id} from inbox (filed under Confirmed)")
    except Exception as e:
        logger.error(f"Archive error for message {msg_id}: {e}")

def label_declined(service, msg_id):
    """Purple — owner declined."""
    apply_label(service, msg_id, 'Rim Repairs/Declined',
                remove_labels=['Rim Repairs/Pending Reply', 'Rim Repairs/Awaiting Confirmation', 'Rim Repairs/Confirmed', 'Rim Repairs/Processed'])

def label_processed(service, msg_id):
    """Grey — processed, no action needed."""
    apply_label(service, msg_id, 'Rim Repairs/Processed',
                remove_labels=['Rim Repairs/Pending Reply', 'Rim Repairs/Awaiting Confirmation', 'Rim Repairs/Confirmed', 'Rim Repairs/Declined'])
