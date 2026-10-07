"""Credential and session operations independent of HTTP transport."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiProblem
from app.core.settings import Settings
from app.database.auth_models import AuthSession, PasswordResetToken
from app.database.base import utc_now
from app.database.models import Account, AccountUser, User
from app.schemas.auth import (
    AuthAccountResponse,
    AuthSessionResponse,
    AuthUserResponse,
    UnitPreferences,
)

passwords = PasswordHash.recommended()
_dummy_hash = passwords.hash(secrets.token_urlsafe(32))


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return digest(f"csrf:{token}")


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def verify_password(value: str, stored: str | None) -> bool:
    try:
        valid = passwords.verify(value, stored or _dummy_hash)
    except Exception:
        return False
    return bool(stored) and valid


@dataclass(frozen=True)
class Principal:
    user: User
    account: Account
    membership: AccountUser
    session: AuthSession
    token: str

    @property
    def account_id(self) -> str:
        return self.account.id

    @property
    def user_id(self) -> str:
        return self.user.id

    def require_write(self) -> None:
        if self.membership.role not in {"owner", "admin", "editor"}:
            raise ApiProblem(403, "write_access_required", "This workspace is read only.")

    def response(self) -> AuthSessionResponse:
        try:
            units = UnitPreferences.model_validate(self.user.unit_preferences or {})
        except ValueError:
            units = UnitPreferences()
        return AuthSessionResponse(
            user=AuthUserResponse(
                id=self.user.id,
                email=self.user.email,
                display_name=self.user.display_name or "",
                school=self.user.school,
                unit_preferences=units,
            ),
            account=AuthAccountResponse(
                id=self.account.id, name=self.account.name, role=self.membership.role
            ),
            csrf_token=csrf_token(self.token),
            expires_at=aware(self.session.expires_at),
        )


def find_user(session: Session, email: str, *, lock: bool = False) -> User | None:
    statement = select(User).where(func.lower(User.email) == email.lower())
    return session.scalar(statement.with_for_update() if lock else statement)


def create_session(session: Session, user: User, settings: Settings) -> Principal:
    membership = session.scalar(
        select(AccountUser)
        .join(Account)
        .where(AccountUser.user_id == user.id)
        .order_by(Account.created_at, Account.id)
        .limit(1)
    )
    if membership is None:
        raise ApiProblem(
            403, "workspace_unavailable", "No workspace is available for this account."
        )
    token = secrets.token_urlsafe(32)
    now = utc_now()
    session.execute(
        delete(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.expires_at <= now)
        .execution_options(synchronize_session=False)
    )
    record = AuthSession(
        token_hash=digest(token),
        user_id=user.id,
        account_id=membership.account_id,
        auth_version=user.auth_version,
        expires_at=now + timedelta(seconds=settings.session_lifetime_seconds),
    )
    session.add(record)
    session.flush()
    return Principal(user, membership.account, membership, record, token)


def get_principal(session: Session, token: str | None) -> Principal:
    if not token or len(token) > 128:
        raise ApiProblem(401, "authentication_required", "Sign in to continue.")
    record = session.scalar(select(AuthSession).where(AuthSession.token_hash == digest(token)))
    if record is None or aware(record.expires_at) <= utc_now():
        raise ApiProblem(401, "session_expired", "Your session has expired. Sign in again.")
    user = session.get(User, record.user_id)
    membership = session.get(AccountUser, (record.account_id, record.user_id))
    if user is None or membership is None or user.auth_version != record.auth_version:
        raise ApiProblem(401, "session_expired", "Your session has expired. Sign in again.")
    return Principal(user, membership.account, membership, record, token)


def invalidate_credentials(session: Session, user: User, password: str) -> None:
    user.password_hash = passwords.hash(password)
    user.auth_version += 1
    session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
