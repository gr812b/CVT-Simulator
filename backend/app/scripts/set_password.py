"""Operator-only credential setup for an existing, trusted account owner.

Run from backend/: python -m app.scripts.set_password user@example.com
Passwords are read from a terminal, never command-line arguments or seed files.
"""

import argparse
from getpass import getpass

from app.application.auth import find_user, invalidate_credentials
from app.core.settings import Settings
from app.database.session import make_engine, make_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Existing user whose identity you have verified")
    args = parser.parse_args()
    factory = make_session_factory(
        make_engine(Settings.from_environment().database_url)
    )
    with factory.begin() as session:
        user = find_user(session, args.email.strip().lower(), lock=True)
        if user is None:
            parser.error(
                "No existing user has that email. Register a new account in the app."
            )
        password = getpass("New password (12–128 characters): ")
        if not 12 <= len(password) <= 128:
            parser.error("Password must contain 12–128 characters.")
        if getpass("Confirm new password: ") != password:
            parser.error("Passwords do not match.")
        invalidate_credentials(session, user, password)
    print("Password updated. Existing sessions and reset links have been revoked.")


if __name__ == "__main__":
    main()
