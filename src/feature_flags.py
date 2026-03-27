"""
feature_flags.py — Runtime feature toggles stored in the existing SQLite app_state table.

All flags default to True (enabled) if not yet stored.
Uses the same DB connection + WAL mode as the rest of the system, so concurrent
access from another agent or process is safe.
"""

from state_manager import StateManager

# Key → (display label, short description)
FLAGS = {
    'flag_auto_email_replies': (
        'Auto email replies to customers',
        'Send clarification emails when booking info is missing',
    ),
    'flag_auto_sms_owner': (
        'Auto SMS booking requests to owner',
        'Sends new booking details to your phone for YES/NO confirmation',
    ),
    'flag_auto_sms_customer': (
        'Auto SMS to customers',
        'Send confirmation or decline SMS to customers after owner decision',
    ),
    'flag_auto_email_customer': (
        'Auto email to customers',
        'Send confirmation or decline emails to customers after owner decision',
    ),
    'flag_day_prior_reminders': (
        'Morning reminder SMS (day-prior)',
        'Send customers an SMS reminder the morning before their booking',
    ),
    'flag_post_job_reviews': (
        'Post-job review request SMS',
        'Send a Google review request ~3 hours after job completion',
    ),
}


def get_flag(key: str) -> bool:
    """Return True if the flag is enabled. Defaults to True if never set."""
    state = StateManager()
    val = state.get_app_state(key)
    if val is None:
        return True
    return val.lower() == 'true'


def set_flag(key: str, enabled: bool) -> None:
    """Persist a feature flag to SQLite."""
    state = StateManager()
    state.set_app_state(key, 'true' if enabled else 'false')


def get_all_flags() -> dict:
    """Return {key: {label, description, enabled}} for every registered flag."""
    return {
        key: {
            'label': label,
            'description': desc,
            'enabled': get_flag(key),
        }
        for key, (label, desc) in FLAGS.items()
    }
