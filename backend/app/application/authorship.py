"""Public display names for library and run attribution; never expose email."""

from app.database.models import User
from app.database.seed import SEED_USER_ID


def author_name(session, user_id):
    if user_id == SEED_USER_ID:
        return "CINDER · McMaster Baja"
    user = session.get(User, user_id) if user_id else None
    return user.display_name if user and user.display_name else "CINDER member"
