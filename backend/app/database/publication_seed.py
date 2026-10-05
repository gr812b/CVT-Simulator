"""Seed public snapshots for every physical catalog entry."""

from types import SimpleNamespace

from sqlalchemy import select

from app.application import physical_library, publications
from app.database import library
from app.database.seed import SEED_ACCOUNT_ID


def seed_publications(session):
    principal = SimpleNamespace(account_id=SEED_ACCOUNT_ID)
    for kind, resource in physical_library.RESOURCES.items():
        model = library.binding_for(resource).object_model
        for obj in session.scalars(
            select(model).where(
                model.account_id == SEED_ACCOUNT_ID,
                model.released_version_id.is_not(None),
                model.lifecycle_status != "archived",
            )
        ):
            publications.publish_saved_revision(
                session, principal, kind, obj, author="CINDER catalog", sample=True
            )


def seed_publication_fixtures(session, *, account_id, setup_revision_id, label):
    principal = SimpleNamespace(account_id=account_id)
    rev = physical_library._revision(session, principal, "setups", setup_revision_id)
    obj = physical_library._parent(session, "setups", rev)
    publications.publish_saved_revision(
        session, principal, "setups", obj, author=f"Development fixture {label.upper()}"
    )
