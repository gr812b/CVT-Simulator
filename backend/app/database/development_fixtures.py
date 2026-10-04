"""Opt-in deterministic ownership fixtures, separate from the sample catalog.

No default password is assigned. Use the operator password command when a
local browser login is needed. Existing fixtures, including edits, are retained.
"""

import copy

from sqlalchemy.orm import Session

from app.database import library
from app.database.models import Account, AccountUser, User
from app.database.physical_seed import sample_id


def seed_development_fixtures(session: Session) -> None:
    for label in ("a", "b"):
        user_id = sample_id(f"fixture:user:{label}")
        account_id = sample_id(f"fixture:account:{label}")
        if session.get(User, user_id) is None:
            session.add(
                User(
                    id=user_id,
                    email=f"m2-owner-{label}@example.test",
                    display_name=f"M2 Owner {label.upper()}",
                )
            )
        if session.get(Account, account_id) is None:
            session.add(
                Account(
                    id=account_id,
                    name=f"M2 Ownership Fixture {label.upper()}",
                    tier="free",
                )
            )
        session.flush()
        if session.get(AccountUser, (account_id, user_id)) is None:
            session.add(
                AccountUser(account_id=account_id, user_id=user_id, role="owner")
            )
            session.flush()

        def copy_component(resource: str, source_key: str, *, refs=None):
            key = f"fixture:{label}:{resource}"
            binding = library.binding_for(resource)
            existing = session.get(binding.object_model, sample_id(key))
            if existing is not None:
                return existing.released_version_id
            source = session.get(binding.version_model, sample_id(source_key))
            payload = copy.deepcopy(getattr(source, binding.payload_attr))
            name = f"Fixture {label.upper()} · {resource}"
            obj = library.create_object(
                session,
                resource=resource,
                data={
                    "id": sample_id(key),
                    "account_id": account_id,
                    "name": name,
                    "visibility": "private",
                    "draft_payload": payload,
                    "forked_from_version_id": source.id,
                    "source_label": "Development fixture copied from a fixed project sample",
                },
            )
            release = {
                "id": sample_id(f"{key}:r1"),
                "payload": payload,
                "created_by_user_id": user_id,
                "visibility_at_release": "private",
                "release_notes": "Isolated local ownership fixture.",
            }
            if resource == "cvt-designs":
                release["tuning_schema"] = copy.deepcopy(source.tuning_schema)
            if refs:
                release.update(refs)
            version = library.release_object(
                session, resource=resource, object_id=obj.id, release_data=release
            )
            if resource == "cvt-designs":
                version.belt_version_id = refs["belt_version_id"]
            return version.id

        engine_id = copy_component("engines", "engine:r1")
        belt_id = copy_component("belts", "belt:r1")
        cvt_id = copy_component(
            "cvt-designs", "cvt:r1", refs={"belt_version_id": belt_id}
        )
        output_id = copy_component("output-systems", "vehicle:r2")
        setup_revision_id = copy_component(
            "vehicle-assemblies",
            "setup:r2",
            refs={
                "engine_version_id": engine_id,
                "cvt_design_version_id": cvt_id,
                "output_system_version_id": output_id,
                "assembly_payload": {},
            },
        )
        from app.database.experiment_seed import seed_experiment_fixtures

        seed_experiment_fixtures(
            session,
            account_id=account_id,
            user_id=user_id,
            setup_revision_id=setup_revision_id,
            label=label,
        )
    session.flush()
