"""Browse public authors and the shared school catalog."""

from app.api.v1.dependencies import get_database_session
from app.application import access
from app.application.schools import school_catalog
from app.database.models import User
from app.schemas.community import PublicUser, PublicUserPage, SchoolCatalog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/schools", response_model=SchoolCatalog)
def schools():
    return school_catalog()


@router.get("/users", response_model=PublicUserPage)
def users(
    q: str = Query(default="", max_length=200),
    school: str = Query(default="", max_length=200),
    user_id: str | None = None,
    limit: int = Query(default=24, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_database_session),
):
    conditions = [User.password_hash.is_not(None)]
    if q.strip():
        pattern = (
            "%"
            + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        conditions.append(
            or_(
                User.display_name.ilike(pattern, escape="\\"),
                User.school.ilike(pattern, escape="\\"),
            )
        )
    if school:
        conditions.append(User.school == school)
    if user_id:
        conditions.append(User.id == user_id)
    rows = session.execute(
        select(User.id, User.display_name, User.school)
        .where(*conditions)
        .order_by(func.lower(User.display_name), User.id)
        .offset(offset)
        .limit(limit)
    )
    return PublicUserPage(
        items=[
            PublicUser(
                id=row.id,
                display_name=row.display_name or "CINDER member",
                school=row.school,
            )
            for row in rows
        ],
        total=session.scalar(select(func.count()).select_from(User).where(*conditions)),
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=PublicUser)
def user_profile(user_id: str, session: Session = Depends(get_database_session)):
    user = session.scalar(
        select(User).where(User.id == user_id, User.password_hash.is_not(None))
    )
    if user is None:
        raise access.unavailable()
    return PublicUser(
        id=user.id,
        display_name=user.display_name or "CINDER member",
        school=user.school,
    )
