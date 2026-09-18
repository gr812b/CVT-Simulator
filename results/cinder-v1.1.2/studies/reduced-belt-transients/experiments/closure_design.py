"""Focused closure designs for unresolved reduced-belt questions.

These are deliberately small mechanism-driven stress families, not tune
optimizations.  Friction coefficients are never changed to manufacture contact
utilization.  Instead, one pulley clamp mechanism at a time is weakened so the
normal CINDER hybrid contact logic decides when stick capacity is exhausted.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ContactStressCase:
    name: str
    title: str
    primary_flyweight_scale: float = 1.0
    secondary_reaction_scale: float = 1.0
    start_time_s: float = 1.80
    rise_time_s: float = 0.10
    target_grade_deg: float = 30.0
    purpose: str = "high_contact"

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_flyweight_scale", self.primary_flyweight_scale),
            ("secondary_reaction_scale", self.secondary_reaction_scale),
            ("start_time_s", self.start_time_s),
            ("rise_time_s", self.rise_time_s),
            ("target_grade_deg", self.target_grade_deg),
        ):
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.primary_flyweight_scale <= 0.0 or self.secondary_reaction_scale <= 0.0:
            raise ValueError("clamp stress scales must be strictly positive")
        if self.start_time_s < 0.0 or self.rise_time_s < 0.0:
            raise ValueError("times must be non-negative")

    def as_protocol(self) -> dict[str, object]:
        return {
            "name": self.name,
            "title": self.title,
            "family": "contact_closure",
            "purpose": (
                "Focused contact-demand stress case. Static and kinetic friction are unchanged; "
                "one or both clamp mechanisms are weakened so CINDER's normal hybrid logic "
                "determines whether the trajectory remains stick, enters mixed slip, or both-slip."
            ),
            "contact_stress": {
                "primary_flyweight_scale": self.primary_flyweight_scale,
                "secondary_reaction_scale": self.secondary_reaction_scale,
            },
            "controlled_load": {
                "kind": "smooth_time_programmed_grade",
                "start_time_s": self.start_time_s,
                "rise_time_s": self.rise_time_s,
                "target_grade_deg": self.target_grade_deg,
            },
        }


@dataclass(frozen=True, slots=True)
class InertiaContinuationCase:
    name: str
    title: str
    scenario: str
    kind: str
    scale: float

    def __post_init__(self) -> None:
        if self.kind not in {"reference", "global_transport", "coherent_density"}:
            raise ValueError(f"unknown inertia continuation kind: {self.kind}")
        if not isfinite(float(self.scale)) or self.scale <= 0.0:
            raise ValueError("inertia continuation scale must be positive and finite")


def build_contact_stress_cases() -> tuple[ContactStressCase, ...]:
    cases: list[ContactStressCase] = []
    # Primary-only stress: scale only the fixed-pivot flyweight mass/moments.
    for scale in (0.90, 0.75, 0.60, 0.45, 0.30):
        tag = f"{int(round(scale*100)):02d}"
        cases.append(ContactStressCase(
            name=f"contact_primary_{tag}",
            title=f"Primary clamp stress: flyweight actuation {scale:.2f}x",
            primary_flyweight_scale=scale,
            secondary_reaction_scale=1.0,
        ))
    # Secondary-only stress: scale spring and torsional reaction together.
    for scale in (0.80, 0.65, 0.50, 0.35, 0.20):
        tag = f"{int(round(scale*100)):02d}"
        cases.append(ContactStressCase(
            name=f"contact_secondary_{tag}",
            title=f"Secondary clamp stress: reaction {scale:.2f}x",
            primary_flyweight_scale=1.0,
            secondary_reaction_scale=scale,
        ))
    # Combined cases seek both-slip and stronger asymmetry without touching mu.
    for p, s in ((0.70, 0.50), (0.55, 0.35), (0.40, 0.20)):
        cases.append(ContactStressCase(
            name=f"contact_combined_p{int(round(100*p)):02d}_s{int(round(100*s)):02d}",
            title=f"Combined clamp stress: primary {p:.2f}x / secondary {s:.2f}x",
            primary_flyweight_scale=p,
            secondary_reaction_scale=s,
        ))
    return tuple(cases)


def apply_contact_stress(document: dict, case: ContactStressCase) -> None:
    """Apply one clamp-stress case to a simulation document in-place."""
    primary_components = document["assembly"]["pulleys"]["primary"]["components"]
    found_flyweight = False
    for component in primary_components:
        if component.get("kind") != "fixed_pivot_roller_flyweight":
            continue
        mass = component["mass_geometry"]
        for key in (
            "mass_per_flyweight_kg",
            "first_moment_u_kg_m",
            "first_moment_v_kg_m",
            "second_moment_u_kg_m2",
            "second_moment_v_kg_m2",
            "product_moment_uv_kg_m2",
            "second_moment_z_kg_m2",
        ):
            mass[key] = float(mass[key]) * case.primary_flyweight_scale
        found_flyweight = True
        break
    if not found_flyweight:
        raise RuntimeError("contact stress expected fixed_pivot_roller_flyweight on primary")

    secondary_components = document["assembly"]["pulleys"]["secondary"]["components"]
    found_spring = False
    found_torsion = False
    for component in secondary_components:
        if component.get("kind") == "axial_spring":
            component["stiffness_N_per_m"] = float(component["stiffness_N_per_m"]) * case.secondary_reaction_scale
            found_spring = True
        elif component.get("kind") == "helical_torque_reaction":
            component["torsional_stiffness_Nm_per_rad"] = float(component["torsional_stiffness_Nm_per_rad"]) * case.secondary_reaction_scale
            found_torsion = True
    if not (found_spring and found_torsion):
        raise RuntimeError("contact stress expected secondary axial spring and helical torque reaction")


def apply_belt_density_scale(document: dict, scale: float) -> None:
    """Scale belt density coherently, changing both m_b and q together."""
    scale = float(scale)
    if not isfinite(scale) or scale <= 0.0:
        raise ValueError("density scale must be positive and finite")
    inertias = document["assembly"]["inertias"]
    inertias["belt_density_kg_per_m3"] = float(inertias["belt_density_kg_per_m3"]) * scale


def build_inertia_continuations() -> tuple[InertiaContinuationCase, ...]:
    cases: list[InertiaContinuationCase] = []
    for scenario in ("flat", "fast_backshift", "fast_unload"):
        cases.append(InertiaContinuationCase(
            name=f"inertia_{scenario}_reference",
            title=f"{scenario.replace('_', ' ').title()} — full belt inertia",
            scenario=scenario,
            kind="reference",
            scale=1.0,
        ))
        for kind, prefix in (("global_transport", "global"), ("coherent_density", "density")):
            for scale in (0.10, 0.03):
                tag = f"{int(round(scale*100)):02d}"
                cases.append(InertiaContinuationCase(
                    name=f"inertia_{scenario}_{prefix}_{tag}",
                    title=f"{scenario.replace('_', ' ').title()} — {kind.replace('_', ' ')} {scale:.2f}x",
                    scenario=scenario,
                    kind=kind,
                    scale=scale,
                ))
    return tuple(cases)
