"""Real SQLite checks for curated roads, safe reseeding and seed attribution."""

from copy import deepcopy
import math
import unittest

from sqlalchemy import select

from app.api.v1.dependencies import PublicReader
from app.application.authorship import author_name, public_author_id
from app.application.experiments import get_revision, list_items
from app.application.roads import (
    default_scenario,
    demo_scenario,
    feature_templates,
    resolve_road,
    validate_scenario,
)
from app.core.settings import Settings
from app.database.base import Base
from app.database.experiment_models import Experiment, ExperimentRevision
from app.database.experiment_seed import _seed_scenarios
from app.database.hashing import canonical_json_hash
from app.database.models import Account, User
from app.database.physical_seed import sample_id
from app.database.seed import SEED_ACCOUNT_ID, SEED_USER_ID, seed_database
from app.database.session import make_engine, make_session_factory
from app.schemas.experiments import ScenarioDocument, SpatialRoad


class CatalogDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = make_session_factory(self.engine)()
        self.session.add_all(
            [
                Account(id=SEED_ACCOUNT_ID, name="CINDER"),
                User(id=SEED_USER_ID, email="demo@mcmaster-baja.example", display_name="CINDER"),
                Account(id="member-account", name="My workspace"),
                User(id="member-user", email="member@example.test", display_name="Road builder"),
            ]
        )
        self.session.commit()
        self.principal = PublicReader()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add_sample(self, key, documents, *, account_id=SEED_ACCOUNT_ID, is_sample=True):
        obj = Experiment(
            id=sample_id(f"scenario:{key}"),
            account_id=account_id,
            kind="scenarios",
            name=documents[-1].name,
            is_sample=is_sample,
        )
        self.session.add(obj)
        self.session.flush()
        revisions = []
        for number, document in enumerate(documents, 1):
            payload = document.model_dump(mode="json")
            revision = ExperimentRevision(
                id=sample_id(f"scenario:{key}:r{number}"),
                experiment_id=obj.id,
                number=number,
                document=payload,
                content_hash=canonical_json_hash(payload),
                created_by_user_id=SEED_USER_ID,
            )
            self.session.add(revision)
            self.session.flush()
            obj.current_revision_id = revision.id
            revisions.append(revision)
        self.session.commit()
        return obj, revisions

    def document(self, key):
        obj = self.session.get(Experiment, sample_id(f"scenario:{key}"))
        revision = self.session.get(ExperimentRevision, obj.current_revision_id)
        return ScenarioDocument.model_validate(revision.document)

    @staticmethod
    def old_grade(angle):
        return ScenarioDocument(
            kind="scenarios",
            name=f"Old {angle} degree road",
            road=SpatialRoad(
                features=[
                    {
                        "id": f"grade-{angle}",
                        "kind": "slope",
                        "angle_rad": math.radians(angle),
                        "length_m": 1000,
                    }
                ],
                endpoint="continue_grade",
            ),
        )

    def snapshot(self):
        return {
            row.id: (deepcopy(row.document), row.content_hash, row.number)
            for row in self.session.scalars(select(ExperimentRevision))
        }

    def test_new_defaults_resolve_to_requested_roads(self):
        _seed_scenarios(self.session)
        items = list_items(self.session, self.principal, "scenarios")
        self.assertEqual(len(items), 8)
        grade_keys = {sample_id(f"scenario:grade:{angle}") for angle in (-30, -15, 15, 30)}
        self.assertEqual(
            {item.id for item in items if "uphill" in item.name or "downhill" in item.name},
            grade_keys,
        )
        for key in ("flat", "hill", "whoops", "grade:-30", "grade:-15", "grade:15", "grade:30"):
            with self.subTest(key=key):
                self.assertEqual(validate_scenario(self.document(key), Settings()).length_m, 200)
        for angle in (-30, -15, 15, 30):
            document = self.document(f"grade:{angle}")
            road = resolve_road(document.road, Settings())
            self.assertEqual(len(road.profile.segments), 1)
            self.assertAlmostEqual(math.degrees(road.profile.segments[0].grade_angle_rad), angle)
            self.assertAlmostEqual(road.points[-1].elevation_m, 200 * math.sin(math.radians(angle)))
        hill = resolve_road(self.document("hill").road, Settings())
        self.assertEqual([s.start_distance_m for s in hill.profile.segments], [0, 20, 110, 200])
        self.assertAlmostEqual(math.degrees(hill.profile.segments[1].grade_angle_rad), 20)
        self.assertAlmostEqual(math.degrees(hill.profile.segments[2].grade_angle_rad), -20)
        self.assertAlmostEqual(hill.points[-1].elevation_m, 0)
        whoops = resolve_road(self.document("whoops").road, Settings())
        self.assertEqual([s.start_distance_m for s in whoops.sections], [0, 5, 37])
        self.assertAlmostEqual(whoops.maximum_elevation_m, 0.8)
        self.assertGreater(math.degrees(whoops.maximum_absolute_grade_rad), 30)
        self.assertEqual(len(whoops.sections[1].points), 8 * 8 + 1)
        self.assertEqual(self.document("demo-course"), demo_scenario())
        self.assertEqual(resolve_road(demo_scenario().road, Settings()).length_m, 160)
        self.assertEqual(resolve_road(default_scenario().road, Settings()).length_m, 200)
        self.assertEqual(feature_templates()[0]["length_m"], 20)

    def test_existing_samples_append_revisions_and_reseed_idempotently(self):
        grades = {}
        for angle in (-15, 15):
            grades[angle], _ = self.add_sample(f"grade:{angle}", [self.old_grade(angle)])
        whoops_documents = [
            ScenarioDocument(
                kind="scenarios",
                name="CINDER Default · whoops",
                notes=note,
                road=SpatialRoad(
                    features=[
                        {"id": "flat", "kind": "flat", "length_m": 20},
                        {
                            "id": "whoops",
                            "kind": "whoops",
                            "height_m": height,
                            "spacing_m": spacing,
                            "count": 5,
                        },
                    ]
                ),
            )
            for height, spacing, note in (
                (0.4, 6, ""),
                (0.3, 8, "Revision 2: gentler, wider whoops for editor/history practice."),
            )
        ]
        whoops, _ = self.add_sample("whoops", whoops_documents)
        demo, _ = self.add_sample("demo-course", [demo_scenario()])
        demo_revision = demo.current_revision_id
        copied, _ = self.add_sample(
            "member-whoops-copy",
            whoops_documents[-1:],
            account_id="member-account",
            is_sample=False,
        )
        copy_revision = copied.current_revision_id
        original = self.snapshot()

        _seed_scenarios(self.session)
        self.session.commit()
        for revision_id, snapshot in original.items():
            self.assertEqual(self.snapshot()[revision_id], snapshot)
        self.assertEqual(self.session.get(ExperimentRevision, whoops.current_revision_id).number, 3)
        for obj in grades.values():
            self.assertEqual(
                self.session.get(ExperimentRevision, obj.current_revision_id).number, 2
            )
        self.assertEqual(demo.current_revision_id, demo_revision)
        self.assertEqual(copied.current_revision_id, copy_revision)
        self.assertFalse(copied.archived)

        after = self.snapshot()
        pointers = {
            row.id: row.current_revision_id for row in self.session.scalars(select(Experiment))
        }
        _seed_scenarios(self.session)
        self.session.commit()
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(
            {row.id: row.current_revision_id for row in self.session.scalars(select(Experiment))},
            pointers,
        )

    def test_replaced_presets_are_hidden_but_revisions_still_resolve(self):
        retired = []
        for angle in (-10, -5, 5, 10):
            obj, revisions = self.add_sample(f"grade:{angle}", [self.old_grade(angle)])
            retired.append((obj, revisions[0]))
        original = self.snapshot()
        _seed_scenarios(self.session)
        self.session.commit()

        listed = {item.id for item in list_items(self.session, self.principal, "scenarios")}
        history_listed = {
            item.id
            for item in list_items(self.session, self.principal, "scenarios", include_archived=True)
        }
        for obj, revision in retired:
            self.assertTrue(obj.archived)
            self.assertNotIn(obj.id, listed)
            self.assertIn(obj.id, history_listed)
            self.assertEqual(obj.current_revision_id, revision.id)
            selected = get_revision(self.session, self.principal, revision.id, "scenarios")
            self.assertEqual(selected.document, original[revision.id][0])
            self.assertEqual(
                resolve_road(
                    ScenarioDocument.model_validate(selected.document).road, Settings()
                ).length_m,
                1000,
            )

    def test_curated_updates_and_retirement_do_not_touch_nonseed_objects(self):
        protected = []
        for key, account_id, is_sample in (
            ("grade:15", "member-account", True),
            ("grade:-15", SEED_ACCOUNT_ID, False),
            ("grade:5", "member-account", True),
            ("grade:-5", SEED_ACCOUNT_ID, False),
        ):
            obj, _ = self.add_sample(
                key, [self.old_grade(5)], account_id=account_id, is_sample=is_sample
            )
            protected.append((obj, obj.current_revision_id, obj.name))
        original = self.snapshot()
        _seed_scenarios(self.session)
        self.session.commit()
        for obj, revision_id, name in protected:
            self.assertEqual(obj.current_revision_id, revision_id)
            self.assertEqual(obj.name, name)
            self.assertFalse(obj.archived)
            self.assertEqual(self.snapshot()[revision_id], original[revision_id])


class SeedAccountTests(unittest.TestCase):
    def test_full_initializer_renames_seed_only_and_preserves_login(self):
        engine = make_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        try:
            with make_session_factory(engine)() as session:
                seed_database(session)
                session.commit()
                seed_user = session.get(User, SEED_USER_ID)
                seed_account = session.get(Account, SEED_ACCOUNT_ID)
                self.assertEqual((seed_account.name, seed_user.display_name), ("CINDER", "CINDER"))
                login = (seed_user.email, seed_user.password_hash)
                seed_account.name = "Demo Baja Workspace"
                seed_user.display_name = "Demo Baja User"
                session.add_all(
                    [
                        Account(id="member-account", name="My workspace"),
                        User(
                            id="member-user",
                            email="member@example.test",
                            display_name="Road builder",
                        ),
                    ]
                )
                session.commit()
                revision_ids = set(session.scalars(select(ExperimentRevision.id)))

                seed_database(session)
                session.commit()
                self.assertEqual((seed_account.name, seed_user.display_name), ("CINDER", "CINDER"))
                self.assertEqual((seed_user.email, seed_user.password_hash), login)
                self.assertEqual(session.get(Account, "member-account").name, "My workspace")
                self.assertEqual(author_name(session, "member-user"), "Road builder")
                self.assertEqual(author_name(session, SEED_USER_ID), "CINDER")
                self.assertIsNone(public_author_id(session, SEED_USER_ID))
                self.assertEqual(set(session.scalars(select(ExperimentRevision.id))), revision_ids)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
