"""Bilateral/slotted secondary-helix topology for v1.1.2 results."""
from __future__ import annotations

from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator
from cinder.model.system import MechanicalCVTPlant


class BilateralHelicalTorqueReactionForce(HelicalTorqueReactionForce):
    """Production helix equations with a zero-clearance bilateral slot."""

    compressive_contact_margin = None
    has_compressive_contact = None


def use_bilateral_secondary_helix(plant: MechanicalCVTPlant) -> int:
    """Replace production secondary helix laws by bilateral twins in ``plant``."""
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
    return changed
