"""Public display names for library and run attribution; never expose email."""

from app.database.models import User
from app.database.seed import SEED_DISPLAY_NAME, SEED_USER_ID


def author_name(session, user_id):
    if user_id == SEED_USER_ID:
        return SEED_DISPLAY_NAME
    user = session.get(User, user_id) if user_id else None
    return user.display_name if user and user.display_name else "CINDER member"


def public_author_id(session, user_id):
    if not user_id or user_id == SEED_USER_ID:
        return None
    user = session.get(User, user_id)
    return user.id if user and user.password_hash else None
