"""Cookie authentication and personal workspace onboarding."""

import secrets
from datetime import timedelta

from app.api.v1.dependencies import (
    get_current_principal,
    get_database_session,
    require_browser_request,
)
from app.application.auth import (
    Principal,
    aware,
    create_session,
    digest,
    find_user,
    invalidate_credentials,
    passwords,
    verify_password,
)
from app.application.auth_limits import throttle, throttle_ip
from app.application.mail import send_password_reset
from app.core.errors import ApiProblem
from app.database.auth_models import AuthSession, PasswordResetToken
from app.database.base import utc_now
from app.database.models import Account, AccountUser, User
from app.schemas.auth import (
    AuthMessageResponse,
    AuthSessionResponse,
    ChangePasswordRequest,
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UnitPreferences,
    UpdateProfileRequest,
)
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    dependencies=[Depends(require_browser_request)],
)


def _set_cookie(request: Request, response: Response, principal: Principal) -> AuthSessionResponse:
    settings = request.app.state.settings
    response.set_cookie(
        settings.session_cookie_name,
        principal.token,
        max_age=settings.session_lifetime_seconds,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api",
    )
    response.headers["Cache-Control"] = "no-store"
    return principal.response()


def _remove_old_cookie_session(request: Request, session: Session) -> None:
    old = request.cookies.get(request.app.state.settings.session_cookie_name)
    if old:
        session.execute(delete(AuthSession).where(AuthSession.token_hash == digest(old)))


@router.post("/register", response_model=AuthSessionResponse, status_code=201)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_database_session),
) -> AuthSessionResponse:
    throttle_ip(request, "register", limit=15)
    user = User(
        email=body.email,
        display_name=body.display_name,
        school=body.school,
        password_hash=passwords.hash(body.password),
        auth_version=0,
    )
    try:
        account = Account(name=f"{body.display_name}’s workspace", tier="free")
        session.add_all([user, account])
        session.flush()
        session.add(AccountUser(account_id=account.id, user_id=user.id, role="owner"))
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ApiProblem(
            409,
            "registration_unavailable",
            "Unable to register. Try signing in or resetting your password.",
        ) from exc
    _remove_old_cookie_session(request, session)
    principal = create_session(session, user, request.app.state.settings)
    session.commit()
    return _set_cookie(request, response, principal)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_database_session),
) -> AuthSessionResponse:
    throttle_ip(request, "login", limit=60)
    throttle(request, "login:email", body.email, limit=15, seconds=900)
    user = find_user(session, body.email, lock=True)
    if not verify_password(body.password, user.password_hash if user else None):
        raise ApiProblem(401, "invalid_credentials", "Email or password is incorrect.")
    _remove_old_cookie_session(request, session)
    principal = create_session(session, user, request.app.state.settings)
    session.commit()
    return _set_cookie(request, response, principal)


@router.get("/session", response_model=AuthSessionResponse)
def current_session(
    response: Response, principal: Principal = Depends(get_current_principal)
) -> AuthSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    return principal.response()


@router.post("/logout", response_model=AuthMessageResponse)
def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_database_session),
) -> AuthMessageResponse:
    session.delete(principal.session)
    session.commit()
    response.delete_cookie(
        request.app.state.settings.session_cookie_name,
        path="/api",
        secure=request.app.state.settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    return AuthMessageResponse(message="Signed out.")


@router.patch("/profile", response_model=AuthSessionResponse)
def profile(
    body: UpdateProfileRequest,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_database_session),
) -> AuthSessionResponse:
    principal.user.display_name = body.display_name
    principal.user.school = body.school
    session.flush()
    return principal.response()


@router.patch("/unit-preferences", response_model=AuthSessionResponse)
def unit_preferences(
    body: UnitPreferences,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_database_session),
) -> AuthSessionResponse:
    # Serialize partial preference updates for the authenticated user only.
    user = session.scalar(
        select(User)
        .where(User.id == principal.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user.unit_preferences = body.apply_to(user.unit_preferences)
    session.flush()
    return principal.response()


@router.post("/password", response_model=AuthSessionResponse)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_database_session),
) -> AuthSessionResponse:
    throttle_ip(request, "change-password", limit=15)
    user = session.scalar(
        select(User)
        .where(User.id == principal.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user.auth_version != principal.session.auth_version:
        raise ApiProblem(401, "session_expired", "Sign in again to change your password.")
    if not verify_password(body.current_password, user.password_hash):
        raise ApiProblem(400, "password_incorrect", "Current password is incorrect.")
    invalidate_credentials(session, user, body.password)
    replacement = create_session(session, user, request.app.state.settings)
    session.commit()
    return _set_cookie(request, response, replacement)


@router.post("/forgot-password", response_model=AuthMessageResponse)
def forgot_password(
    body: EmailRequest,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_database_session),
) -> AuthMessageResponse:
    throttle_ip(request, "forgot-password", limit=20)
    throttle(request, "reset:email", body.email, limit=5, seconds=3600)
    user = find_user(session, body.email, lock=True)
    if user is not None and user.password_hash:
        token = secrets.token_urlsafe(32)
        settings = request.app.state.settings
        session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        session.add(
            PasswordResetToken(
                token_hash=digest(token),
                user_id=user.id,
                auth_version=user.auth_version,
                expires_at=utc_now() + timedelta(seconds=settings.reset_lifetime_seconds),
            )
        )
        session.commit()
        background.add_task(send_password_reset, settings, user.email, token)
    return AuthMessageResponse(
        message="If that email has a CINDER account, a reset link will be sent shortly."
    )


@router.post("/reset-password", response_model=AuthMessageResponse)
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    session: Session = Depends(get_database_session),
) -> AuthMessageResponse:
    throttle_ip(request, "reset-password", limit=20)
    record = session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == digest(body.token))
    )
    invalid = ApiProblem(
        400,
        "reset_link_invalid",
        "This reset link is invalid or expired. Request a new link.",
    )
    if record is None or record.used_at is not None or aware(record.expires_at) <= utc_now():
        raise invalid
    user = session.scalar(select(User).where(User.id == record.user_id).with_for_update())
    if user is None or user.auth_version != record.auth_version:
        raise invalid
    consumed = session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == record.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > utc_now(),
        )
        .values(used_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        raise invalid
    invalidate_credentials(session, user, body.password)
    session.commit()
    return AuthMessageResponse(message="Password updated. Sign in with your new password.")
