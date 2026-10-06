"""Per-tip editor limits use the same SI bound as preview and save validation."""

from copy import deepcopy
import unittest

from app.application.experiment_tuning import apply_values, parameters
from app.application.physical_contracts import baseline_case
from app.core.errors import ApiProblem
from app.database.seed import _baseline_tuning_schema
from app.schemas.experiments import TuneDocument


def tip_inputs():
    assembly = baseline_case()["assembly"]
    schema = _baseline_tuning_schema()
    return assembly, schema, parameters(assembly, schema)


def flyweight(assembly):
    return next(
        component
        for component in assembly["pulleys"]["primary"]["components"]
        if component["kind"] == "fixed_pivot_roller_flyweight"
    )


class TipMassLimitTests(unittest.TestCase):
    def test_tip_metadata_is_per_flyweight_with_500_gram_maximum(self):
        assembly, schema, params = tip_inputs()
        mass = flyweight(assembly)["mass_geometry"]
        field = next(param for param in params if param["key"] == "primary_tip_mass")
        self.assertEqual(field["unit"], "kg")
        self.assertEqual(field["maximum"], 0.5)
        self.assertIn("per flyweight", field["label"])
        self.assertAlmostEqual(
            field["default"],
            mass["mass_per_flyweight_kg"] - schema["flyweight_tip_body_mass_kg"],
        )
        # The illustration's 150 g reference does not change the physical default.
        self.assertAlmostEqual(field["default"], 0.25)

    def test_500_grams_is_accepted_per_tip_with_unchanged_body_and_count(self):
        assembly, schema, params = tip_inputs()
        before = deepcopy(flyweight(assembly))
        apply_values(assembly, params, {"primary_tip_mass": 0.5})
        component = flyweight(assembly)
        mass = component["mass_geometry"]
        body = schema["flyweight_tip_body_mass_kg"]
        length = component["geometry"]["arm_length_m"]
        self.assertAlmostEqual(mass["mass_per_flyweight_kg"], body + 0.5, places=12)
        self.assertAlmostEqual(
            mass["first_moment_u_kg_m"], body * length / 2 + 0.5 * length, places=12
        )
        self.assertAlmostEqual(
            mass["second_moment_u_kg_m2"],
            body * length**2 / 3 + 0.5 * length**2,
            places=12,
        )
        self.assertEqual(
            mass["number_of_flyweights"], before["mass_geometry"]["number_of_flyweights"]
        )
        self.assertEqual(component["geometry"], before["geometry"])

    def test_above_500_grams_is_rejected_before_changing_the_assembly(self):
        for value in (0.501, 0.72):
            with self.subTest(value=value):
                assembly, _schema, params = tip_inputs()
                before = deepcopy(assembly)
                with self.assertRaises(ApiProblem) as caught:
                    apply_values(assembly, params, {"primary_tip_mass": value})
                self.assertEqual(caught.exception.status_code, 422)
                self.assertEqual(caught.exception.code, "tune_value")
                self.assertIn("per flyweight", caught.exception.message)
                self.assertEqual(assembly, before)

    def test_generic_full_flyweight_mass_does_not_get_a_tip_only_limit(self):
        assembly = baseline_case()["assembly"]
        schema = _baseline_tuning_schema()
        schema.pop("flyweight_tip_body_mass_kg")
        params = parameters(assembly, schema)
        field = next(param for param in params if param["key"] == "primary_flyweight_mass")
        self.assertIsNone(field.get("maximum"))
        self.assertTrue(all(param["key"] != "primary_tip_mass" for param in params))
        apply_values(assembly, params, {"primary_flyweight_mass": 0.75})
        self.assertEqual(flyweight(assembly)["mass_geometry"]["mass_per_flyweight_kg"], 0.75)

    def test_saved_older_tip_values_remain_readable_without_rewriting_them(self):
        document = {
            "kind": "tunes",
            "name": "Earlier saved tune",
            "notes": "",
            "cvt_revision_id": "retained-cvt-revision",
            "values": {"primary_tip_mass": 0.72},
        }
        self.assertEqual(TuneDocument.model_validate(document).model_dump(), document)
