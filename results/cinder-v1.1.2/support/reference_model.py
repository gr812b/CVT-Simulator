"""Shared results-side reference-model helpers for CINDER 1.1.2.

The published wheel models the torque-reactive helix as a selected unilateral
flank.  The v1.1.2 results programme uses a zero-clearance bilateral/slotted
secondary helix when a study asks for the shared results reference model.  This
keeps a particular one-flank hardware topology from terminating belt/contact
stress tests.

The slotted element inherits the exact production helix equations: signed belt
torque reaction, torsional preload, movable-member inertia, shaft reaction and
axial force are unchanged.  The only topology change is that the element does
not expose a unilateral ``compressive_contact_margin`` to ``PulleyActuator``.
A negative signed reaction is therefore carried by the opposite slot flank; it
is never absoluted, clipped or removed from the equations.

There is deliberately NO process-global monkey patch, .pth hook, environment
variable or installation step.  A result study that wants the shared reference
model calls ``decode_results_simulation_case_document`` (or applies
``use_slotted_secondary_helix`` to an already-decoded plant).  A study that
intentionally wants the stock released unilateral helix simply uses CINDER's
normal decoder directly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from cinder.contracts import decode_simulation_case_document
from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator
from cinder.model.system import MechanicalCVTPlant

RELEASE_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = RELEASE_ROOT / "defaults" / "results_reference_model.json"


class BilateralHelicalTorqueReactionForce(HelicalTorqueReactionForce):
    """Production helix equations with a bilateral zero-clearance slot topology."""

    # PulleyActuator only treats an element as unilateral when this callable is
    # present.  The signed force/torque equations inherited from production are
    # untouched.
    compressive_contact_margin = None
    has_compressive_contact = None


@dataclass(frozen=True)
class ReferenceModelStatus:
    secondary_helix_topology: str
    policy_path: str
    changed_force_laws: int


def use_slotted_secondary_helix(plant: MechanicalCVTPlant) -> ReferenceModelStatus:
    """Replace only unilateral secondary helix force laws with bilateral twins.

    ``plant`` is mutated in place because decoded systems and later fixed-boundary
    bench systems intentionally share the same frozen plant object.
    """
    actuator = plant.secondary_actuator
    laws = []
    changed = 0
    for law in actuator.force_laws:
        if isinstance(law, BilateralHelicalTorqueReactionForce):
            laws.append(law)
        elif isinstance(law, HelicalTorqueReactionForce):
            laws.append(BilateralHelicalTorqueReactionForce(spec=law.spec))
            changed += 1
        else:
            laws.append(law)
    if changed:
        object.__setattr__(plant, "secondary_actuator", PulleyActuator(*laws))
    return ReferenceModelStatus(
        secondary_helix_topology="bilateral_zero_clearance_slot",
        policy_path=str(POLICY_PATH),
        changed_force_laws=changed,
    )


def decode_results_simulation_case_document(document: Mapping[str, Any]):
    """Decode a public CINDER case and apply the shared v1.1.2 results reference topology."""
    decoded = decode_simulation_case_document(document)
    status = use_slotted_secondary_helix(decoded.plant)
    # The production decoder currently shares one plant between ``decoded.plant``
    # and the composed system.  Assert that rather than silently relying on it.
    if decoded.system.cvt.model is not decoded.plant:
        use_slotted_secondary_helix(decoded.system.cvt.model)
    # Keep the decoded assembly coherent too, so a results study that rebuilds a
    # plant/system from ``decoded.assembly`` retains the same declared topology.
    try:
        object.__setattr__(
            decoded.assembly.pulleys.secondary,
            "actuator",
            decoded.plant.secondary_actuator,
        )
    except (AttributeError, TypeError):
        # The executable plant/system are authoritative for current v1.1.2
        # studies; this is only a coherence aid for callers that rebuild.
        pass
    return decoded


def reference_model_status(plant: MechanicalCVTPlant) -> ReferenceModelStatus:
    changed = sum(
        isinstance(law, BilateralHelicalTorqueReactionForce)
        for law in plant.secondary_actuator.force_laws
    )
    return ReferenceModelStatus(
        secondary_helix_topology=(
            "bilateral_zero_clearance_slot" if changed else "published_unilateral"
        ),
        policy_path=str(POLICY_PATH),
        changed_force_laws=int(changed),
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
