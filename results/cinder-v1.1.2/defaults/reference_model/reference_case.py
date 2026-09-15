"""Canonical executable reference-case loader for CINDER 1.1.2 results."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from cinder.contracts import decode_simulation_case_document
from cinder.model.system import MechanicalCVTPlant

from .slotted_helix import (
    BilateralHelicalTorqueReactionForce,
    use_bilateral_secondary_helix,
)

HERE = Path(__file__).resolve().parent
DEFAULTS_ROOT = HERE.parent
BASE_DOCUMENT_PATH = DEFAULTS_ROOT / "baja" / "simulation_case.json"
POLICY_PATH = HERE / "policy.json"


@dataclass(frozen=True)
class ReferenceModelStatus:
    secondary_helix_topology: str
    policy_path: str
    changed_force_laws: int


def load_reference_document(path: Path | None = None) -> dict[str, Any]:
    source = BASE_DOCUMENT_PATH if path is None else Path(path)
    return json.loads(source.read_text(encoding="utf-8"))


def decode_reference_case(document: Mapping[str, Any] | None = None):
    """Decode public input and apply the v1.1.2 bilateral results topology."""
    if document is None:
        document = load_reference_document()
    decoded = decode_simulation_case_document(document)

    use_bilateral_secondary_helix(decoded.plant)
    if decoded.system.cvt.model is not decoded.plant:
        use_bilateral_secondary_helix(decoded.system.cvt.model)

    try:
        object.__setattr__(
            decoded.assembly.pulleys.secondary,
            "actuator",
            decoded.plant.secondary_actuator,
        )
    except (AttributeError, TypeError):
        pass

    return decoded


def reference_model_status(plant: MechanicalCVTPlant) -> ReferenceModelStatus:
    count = sum(
        isinstance(law, BilateralHelicalTorqueReactionForce)
        for law in plant.secondary_actuator.force_laws
    )
    return ReferenceModelStatus(
        secondary_helix_topology=(
            "bilateral_zero_clearance_slot" if count else "not_reference_bilateral"
        ),
        policy_path=str(POLICY_PATH),
        changed_force_laws=int(count),
    )


def write_reference_model_provenance(
    directory: Path,
    *,
    plant: MechanicalCVTPlant,
    extra: dict[str, Any] | None = None,
) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(reference_model_status(plant))
    if POLICY_PATH.is_file():
        payload["policy_document"] = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if extra:
        payload.update(extra)
    path = directory / "reference_model_policy.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
