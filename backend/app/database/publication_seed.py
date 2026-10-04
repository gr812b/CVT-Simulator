"""Additive, intentionally listed examples and opt-in sharing fixtures."""

from types import SimpleNamespace

from app.application import publications
from app.application.physical_contracts import validate_physical
from app.database.physical_seed import sample_id
from app.database.publication_models import PhysicalPublication
from app.database.seed import SEED_ACCOUNT_ID


def _insert(
    session,
    *,
    key,
    account_id,
    kind,
    revision_id,
    author,
    visibility="public",
    sample=False,
):
    publication_id = sample_id(key)
    if session.get(PhysicalPublication, publication_id):
        return
    principal = SimpleNamespace(account_id=account_id)
    document, revision, dependencies, tuning, fingerprint = publications._bundle(
        session, principal, kind, revision_id
    )
    validation, _ = validate_physical(document)
    if not validation["is_valid"]:
        raise ValueError(f"Publication seed {key} is not valid: {validation}")
    root_id = (
        revision.vehicle_assembly_id if kind == "setups" else revision.cvt_design_id
    )
    session.add(
        PhysicalPublication(
            id=publication_id,
            account_id=account_id,
            kind=kind,
            source_object_id=root_id,
            source_revision_id=revision.id,
            revision_number=revision.version_number,
            publication_number=1,
            name=document.name,
            description=document.description,
            author=author,
            source_label=document.source_label,
            source_url=document.source_url,
            document=document.model_dump(mode="json"),
            dependencies=dependencies,
            tuning_schema=tuning,
            validation=validation,
            snapshot_hash=fingerprint,
            visibility=visibility,
            gallery_listed=visibility == "public",
            sample=sample,
        )
    )
    session.flush()


def seed_publications(session):
    for kind, key, revision_key in (
        ("setups", "setup", "setup:r2"),
        ("setups", "setup-light", "setup-light:r1"),
        ("cvts", "cvt", "cvt:r1"),
        ("cvts", "cvt-alternative", "cvt-alternative:r1"),
    ):
        _insert(
            session,
            key=f"publication:{key}",
            account_id=SEED_ACCOUNT_ID,
            kind=kind,
            revision_id=sample_id(revision_key),
            author="CINDER project samples",
            sample=True,
        )


def seed_publication_fixtures(session, *, account_id, setup_revision_id, label):
    _insert(
        session,
        key=f"fixture:{label}:publication",
        account_id=account_id,
        kind="setups",
        revision_id=setup_revision_id,
        author=f"Development fixture {label.upper()}",
        visibility="public" if label == "a" else "unlisted",
    )
