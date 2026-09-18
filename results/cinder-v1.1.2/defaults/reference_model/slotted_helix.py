"""Bilateral/slotted secondary-helix topology for v1.1.2 results."""
from __future__ import annotations

from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator
from cinder.model.system import MechanicalCVTPlant

BILATERAL_TOPOLOGY = "bilateral_zero_clearance_slot"


def is_bilateral_helix_law(law: object) -> bool:
    """Return whether a helix law explicitly declares the Results slot topology."""
    return getattr(law, "contact_topology", None) == BILATERAL_TOPOLOGY


class BilateralHelicalTorqueReactionForce(HelicalTorqueReactionForce):
    """Production helix equations with a zero-clearance bilateral slot."""

    contact_topology = BILATERAL_TOPOLOGY
    compressive_contact_margin = None
    has_compressive_contact = None


def use_bilateral_secondary_helix(plant: MechanicalCVTPlant) -> int:
    """Apply bilateral topology without replacing explicitly bilateral custom mechanics."""
    actuator = plant.secondary_actuator
    laws = []
    changed = 0
    for law in actuator.force_laws:
        if is_bilateral_helix_law(law):
            laws.append(law)
        elif type(law) is HelicalTorqueReactionForce:
            laws.append(BilateralHelicalTorqueReactionForce(spec=law.spec))
            changed += 1
        elif isinstance(law, HelicalTorqueReactionForce):
            raise TypeError(
                "Custom secondary helix law does not declare a contact topology: "
                f"{type(law).__module__}.{type(law).__qualname__}."
            )
        else:
            laws.append(law)
    if changed:
        object.__setattr__(plant, "secondary_actuator", PulleyActuator(*laws))
    return changed
