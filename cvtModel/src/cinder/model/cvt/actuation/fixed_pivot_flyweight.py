"""Fixed-pivot flyweight maps for a translating roller-ramp follower.

This module implements the mechanism constructed in the formulation appendix:
the pivot is fixed to the pulley, the ramp translates with the movable sheave,
and a rigid roller arm supplies the single relative coordinate ``q_f(x)``.
It deliberately does not claim to be a universal flyweight abstraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from math import atan2, cos, isfinite, pi, sin, sqrt
from typing import Protocol, runtime_checkable

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq, minimize_scalar

from cinder.model.cvt.profiles.types import ScalarProfile


@dataclass(frozen=True, slots=True)
class FixedPivotFlyweightSample:
    """Reduced data required by the fixed-pivot flyweight force law."""

    angle: float
    angle_gradient: float
    angle_curvature: float
    shaft_inertia: float
    shaft_inertia_gradient: float
    pivot_inertia: float

    def __post_init__(self) -> None:
        for name, value in (
            ("angle", self.angle),
            ("angle_gradient", self.angle_gradient),
            ("angle_curvature", self.angle_curvature),
            ("shaft_inertia", self.shaft_inertia),
            ("shaft_inertia_gradient", self.shaft_inertia_gradient),
            ("pivot_inertia", self.pivot_inertia),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if self.angle_gradient <= 0.0:
            raise ValueError(
                "angle_gradient must be positive: local pulley closure must "
                "produce outward flyweight rotation."
            )
        if self.shaft_inertia < 0.0:
            raise ValueError("shaft_inertia must be non-negative.")
        if self.pivot_inertia < 0.0:
            raise ValueError("pivot_inertia must be non-negative.")


@runtime_checkable
class FixedPivotFlyweightMap(Protocol):
    """Configuration map for the present fixed-pivot mechanism class."""

    @property
    def axial_position_min(self) -> float:
        """Smallest supported local pulley-closing position."""

    @property
    def axial_position_max(self) -> float:
        """Largest supported local pulley-closing position."""

    def evaluate(self, axial_position: float) -> FixedPivotFlyweightSample:
        """Return ``q, q', q'', J, J', I`` at one local axial position."""


@dataclass(frozen=True, slots=True)
class ConcentratedTipHardwareMass:
    """Per-flyweight masses approximated at the roller-centre station.

    This is explicitly an input approximation. The finite size and
    centroidal inertia of the individual tip parts are not implied to be
    zero; they are omitted by this convenience reduction.
    """

    roller_bearing_mass_per_flyweight: float = 0.0
    bolt_mass_per_flyweight: float = 0.0
    nut_washer_mass_per_flyweight: float = 0.0
    other_fixed_tip_hardware_mass_per_flyweight: float = 0.0
    tuning_mass_per_flyweight: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            (
                "roller_bearing_mass_per_flyweight",
                self.roller_bearing_mass_per_flyweight,
            ),
            ("bolt_mass_per_flyweight", self.bolt_mass_per_flyweight),
            (
                "nut_washer_mass_per_flyweight",
                self.nut_washer_mass_per_flyweight,
            ),
            (
                "other_fixed_tip_hardware_mass_per_flyweight",
                self.other_fixed_tip_hardware_mass_per_flyweight,
            ),
            ("tuning_mass_per_flyweight", self.tuning_mass_per_flyweight),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")

    @property
    def total_mass_per_flyweight(self) -> float:
        return (
            self.roller_bearing_mass_per_flyweight
            + self.bolt_mass_per_flyweight
            + self.nut_washer_mass_per_flyweight
            + self.other_fixed_tip_hardware_mass_per_flyweight
            + self.tuning_mass_per_flyweight
        )


@dataclass(frozen=True, slots=True)
class FlyweightMassGeometry:
    """Body-fixed mass moments for a circumferentially symmetric flyweight set.

    Moments are supplied for one flyweight in coordinates ``(u, v, z)`` about
    its pivot. ``u`` follows the reference arm line, ``v`` is perpendicular to
    it in the axial-radial plane, and ``z`` is circumferential. The complete set
    contains ``number_of_flyweights`` identical members.

    This representation makes the mass partition explicit: these moments must
    not also be included in the movable-sheave mass or constant pulley inertia.
    """

    number_of_flyweights: int
    mass_per_flyweight: float
    first_moment_u: float
    first_moment_v: float
    second_moment_u: float
    second_moment_v: float
    product_moment_uv: float = 0.0
    second_moment_z: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.number_of_flyweights, bool)
            or not isinstance(self.number_of_flyweights, int)
            or self.number_of_flyweights <= 0
        ):
            raise ValueError("number_of_flyweights must be a positive integer.")
        for name, value in (
            ("mass_per_flyweight", self.mass_per_flyweight),
            ("first_moment_u", self.first_moment_u),
            ("first_moment_v", self.first_moment_v),
            ("second_moment_u", self.second_moment_u),
            ("second_moment_v", self.second_moment_v),
            ("product_moment_uv", self.product_moment_uv),
            ("second_moment_z", self.second_moment_z),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if self.mass_per_flyweight <= 0.0:
            raise ValueError("mass_per_flyweight must be strictly positive.")
        for name, value in (
            ("second_moment_u", self.second_moment_u),
            ("second_moment_v", self.second_moment_v),
            ("second_moment_z", self.second_moment_z),
        ):
            if value < 0.0:
                raise ValueError(f"{name} must be non-negative.")

        tolerance = 256.0 * np.finfo(float).eps
        if self.first_moment_u**2 > (
            self.mass_per_flyweight * self.second_moment_u
        ) * (1.0 + tolerance):
            raise ValueError("first_moment_u is inconsistent with the mass moments.")
        if self.first_moment_v**2 > (
            self.mass_per_flyweight * self.second_moment_v
        ) * (1.0 + tolerance):
            raise ValueError("first_moment_v is inconsistent with the mass moments.")
        if self.product_moment_uv**2 > (
            self.second_moment_u * self.second_moment_v
        ) * (1.0 + tolerance):
            raise ValueError(
                "product_moment_uv is inconsistent with the second moments."
            )

    @classmethod
    def uniform_arm_with_end_mass(
        cls,
        *,
        number_of_flyweights: int,
        arm_length: float,
        arm_mass_per_flyweight: float,
        end_mass_per_flyweight: float,
        second_moment_z_per_flyweight: float = 0.0,
    ) -> "FlyweightMassGeometry":
        """Build the appendix's uniform arm plus concentrated end-mass model."""

        for name, value in (
            ("arm_length", arm_length),
            ("arm_mass_per_flyweight", arm_mass_per_flyweight),
            ("end_mass_per_flyweight", end_mass_per_flyweight),
            ("second_moment_z_per_flyweight", second_moment_z_per_flyweight),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if arm_length <= 0.0:
            raise ValueError("arm_length must be strictly positive.")
        if arm_mass_per_flyweight < 0.0 or end_mass_per_flyweight < 0.0:
            raise ValueError("Arm and end masses must be non-negative.")
        if arm_mass_per_flyweight + end_mass_per_flyweight <= 0.0:
            raise ValueError("At least one flyweight mass must be positive.")
        if second_moment_z_per_flyweight < 0.0:
            raise ValueError("second_moment_z_per_flyweight must be non-negative.")

        first_u = arm_mass_per_flyweight * arm_length / 2.0
        first_u += end_mass_per_flyweight * arm_length
        second_u = arm_mass_per_flyweight * arm_length**2 / 3.0
        second_u += end_mass_per_flyweight * arm_length**2
        return cls(
            number_of_flyweights=number_of_flyweights,
            mass_per_flyweight=(arm_mass_per_flyweight + end_mass_per_flyweight),
            first_moment_u=first_u,
            first_moment_v=0.0,
            second_moment_u=second_u,
            second_moment_v=0.0,
            product_moment_uv=0.0,
            second_moment_z=second_moment_z_per_flyweight,
        )

    @classmethod
    def uniform_slender_arm_with_concentrated_tip_hardware(
        cls,
        *,
        number_of_flyweights: int,
        arm_length: float,
        arm_mass_per_flyweight: float,
        tip_hardware: ConcentratedTipHardwareMass,
        second_moment_z_per_flyweight: float = 0.0,
    ) -> "FlyweightMassGeometry":
        """Build the explicit simplified hardware mass model.

        Assumptions:
        - arm/body is a uniform slender member from pivot to roller centre;
        - all listed tip hardware is concentrated at the roller centre;
        - finite tip-part centroidal inertias are neglected;
        - arm thickness, cut-outs, and nonuniform mass distribution are
          neglected;
        - repeated flyweights are identical.

        For higher fidelity, construct FlyweightMassGeometry directly from
        CAD or measured first/second mass moments.
        """

        if not isinstance(
            tip_hardware,
            ConcentratedTipHardwareMass,
        ):
            raise TypeError(
                "tip_hardware must be a " "ConcentratedTipHardwareMass instance."
            )
        return cls.uniform_arm_with_end_mass(
            number_of_flyweights=number_of_flyweights,
            arm_length=arm_length,
            arm_mass_per_flyweight=arm_mass_per_flyweight,
            end_mass_per_flyweight=(tip_hardware.total_mass_per_flyweight),
            second_moment_z_per_flyweight=(second_moment_z_per_flyweight),
        )

    @property
    def pivot_inertia(self) -> float:
        """Return total ``I_f`` about the circumferential pivot axes."""

        return self.number_of_flyweights * (self.second_moment_u + self.second_moment_v)

    def shaft_inertia(self, *, angle: float, pivot_radius: float) -> float:
        """Return total shaft-axis inertia ``J_f(q)``."""

        sine = sin(angle)
        cosine = cos(angle)
        one = (
            self.mass_per_flyweight * pivot_radius**2
            + 2.0
            * pivot_radius
            * (self.first_moment_u * sine + self.first_moment_v * cosine)
            + self.second_moment_u * sine**2
            + self.second_moment_v * cosine**2
            + 2.0 * self.product_moment_uv * sine * cosine
            + self.second_moment_z
        )
        return self.number_of_flyweights * one

    def shaft_inertia_angle_gradient(
        self, *, angle: float, pivot_radius: float
    ) -> float:
        """Return ``dJ_f/dq`` for the complete flyweight set."""

        sine = sin(angle)
        cosine = cos(angle)
        one = (
            2.0
            * pivot_radius
            * (self.first_moment_u * cosine - self.first_moment_v * sine)
            + 2.0 * (self.second_moment_u - self.second_moment_v) * sine * cosine
            + 2.0 * self.product_moment_uv * (cosine**2 - sine**2)
        )
        return self.number_of_flyweights * one


@dataclass(frozen=True, slots=True)
class PivotedRollerFollowerGeometrySpec:
    """Physical geometry of the appendix roller-follower mechanism."""

    pivot_axial_position: float
    pivot_radius: float
    arm_length: float
    roller_radius: float
    ramp_reference_axial_position: float
    ramp_reference_radius: float
    ramp_profile: ScalarProfile
    axial_position_min: float
    axial_position_max: float
    ramp_axial_direction: int = 1
    roller_side_sign: int = 1
    root_scan_points: int = 257
    validation_positions: int = 33
    root_residual_tolerance: float = 1.0e-14
    coordinate_tolerance: float = 1.0e-10

    def __post_init__(self) -> None:
        for name, value in (
            ("pivot_axial_position", self.pivot_axial_position),
            ("pivot_radius", self.pivot_radius),
            ("arm_length", self.arm_length),
            ("roller_radius", self.roller_radius),
            ("ramp_reference_axial_position", self.ramp_reference_axial_position),
            ("ramp_reference_radius", self.ramp_reference_radius),
            ("axial_position_min", self.axial_position_min),
            ("axial_position_max", self.axial_position_max),
            ("root_residual_tolerance", self.root_residual_tolerance),
            ("coordinate_tolerance", self.coordinate_tolerance),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if self.pivot_radius <= 0.0:
            raise ValueError("pivot_radius must be strictly positive.")
        if self.arm_length <= 0.0:
            raise ValueError("arm_length must be strictly positive.")
        if self.roller_radius <= 0.0:
            raise ValueError("roller_radius must be strictly positive.")
        if self.axial_position_min >= self.axial_position_max:
            raise ValueError("axial_position_min must be less than axial_position_max.")
        if not isinstance(self.ramp_profile, ScalarProfile):
            raise TypeError("ramp_profile must implement ScalarProfile.")
        if self.ramp_axial_direction not in (-1, 1):
            raise ValueError("ramp_axial_direction must be either -1 or +1.")
        if self.roller_side_sign not in (-1, 1):
            raise ValueError("roller_side_sign must be either -1 or +1.")
        if (
            isinstance(self.root_scan_points, bool)
            or not isinstance(self.root_scan_points, int)
            or self.root_scan_points < 33
        ):
            raise ValueError("root_scan_points must be an integer of at least 33.")
        if (
            isinstance(self.validation_positions, bool)
            or not isinstance(self.validation_positions, int)
            or self.validation_positions < 2
        ):
            raise ValueError("validation_positions must be an integer of at least 2.")
        if self.root_residual_tolerance <= 0.0:
            raise ValueError("root_residual_tolerance must be strictly positive.")
        if self.coordinate_tolerance <= 0.0:
            raise ValueError("coordinate_tolerance must be strictly positive.")


@dataclass(frozen=True, slots=True)
class PivotedRollerContactSample:
    """Exact contact solution and its implicit axial derivatives."""

    contact_coordinate: float
    roller_center_axial_position: float
    roller_center_radius: float
    angle: float
    angle_gradient: float
    angle_curvature: float
    contact_residual: float
    offset_regular_factor: float


@dataclass(frozen=True, slots=True)
class PivotedRollerContactCandidate:
    """One instantaneous mathematical arm/roller contact configuration.

    More than one candidate may exist at the same sheave position. They are
    alternative arm orientations, not simultaneous contacts of one roller.

    ``corner_contact`` is true when the roller is contacting a C0 ramp
    junction. In that case the roller centre follows the radius-R arc about
    the physical corner rather than either smooth segment's offset curve.
    """

    contact_coordinate: float
    contact_axial_position: float
    contact_radius: float
    roller_center_axial_position: float
    roller_center_radius: float
    angle: float
    corner_contact: bool = False


@dataclass(frozen=True, slots=True)
class FixedPivotValidationFinding:
    """One geometry/map preflight finding suitable for a UI or CLI."""

    severity: str
    code: str
    message: str
    axial_position: float | None = None
    contact_coordinate: float | None = None

    def __post_init__(self) -> None:
        if self.severity not in ("error", "warning", "info"):
            raise ValueError("severity must be 'error', 'warning', or 'info'.")
        if not self.code or not self.code.strip():
            raise ValueError("code must be non-empty.")
        if not self.message or not self.message.strip():
            raise ValueError("message must be non-empty.")
        for name, value in (
            ("axial_position", self.axial_position),
            ("contact_coordinate", self.contact_coordinate),
        ):
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite when supplied.")

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.axial_position is not None:
            payload["axial_position_m"] = self.axial_position
        if self.contact_coordinate is not None:
            payload["contact_coordinate_m"] = self.contact_coordinate
        return payload


@dataclass(frozen=True, slots=True)
class FixedPivotValidationReport:
    """Full-range construction audit for one fixed-pivot geometry."""

    findings: tuple[FixedPivotValidationFinding, ...]
    requested_positions: int
    traced_positions: int
    minimum_angle_gradient: float | None
    maximum_absolute_angle_curvature: float | None
    maximum_arm_length_error: float | None
    minimum_absolute_offset_regular_factor: float | None
    minimum_ramp_endpoint_margin: float | None
    maximum_mathematical_candidates: int

    @property
    def errors(self) -> tuple[FixedPivotValidationFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "error")

    @property
    def warnings(self) -> tuple[FixedPivotValidationFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "warning")

    @property
    def infos(self) -> tuple[FixedPivotValidationFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "info")

    @property
    def is_valid(self) -> bool:
        return not self.errors and self.traced_positions == self.requested_positions

    def require_valid(self) -> None:
        if self.is_valid:
            return
        details = "\n".join(f"  - [{item.code}] {item.message}" for item in self.errors)
        raise ValueError(
            "Fixed-pivot flyweight geometry failed "
            "construction audit:" + (f"\n{details}" if details else "")
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "requested_positions": self.requested_positions,
            "traced_positions": self.traced_positions,
            "minimum_angle_gradient_per_m": (self.minimum_angle_gradient),
            "maximum_absolute_angle_curvature_per_m2": (
                self.maximum_absolute_angle_curvature
            ),
            "maximum_arm_length_error_m": (self.maximum_arm_length_error),
            "minimum_absolute_offset_regular_factor": (
                self.minimum_absolute_offset_regular_factor
            ),
            "minimum_ramp_endpoint_margin_m": (self.minimum_ramp_endpoint_margin),
            "maximum_mathematical_candidates": (self.maximum_mathematical_candidates),
            "findings": [item.as_dict() for item in self.findings],
        }


class PivotedRollerFollowerGeometry:
    """Exact circle/offset-ramp contact solve from the formulation appendix."""

    def __init__(self, spec: PivotedRollerFollowerGeometrySpec) -> None:
        if not isinstance(spec, PivotedRollerFollowerGeometrySpec):
            raise TypeError("spec must be a PivotedRollerFollowerGeometrySpec.")
        self._spec = spec

    @property
    def spec(self) -> PivotedRollerFollowerGeometrySpec:
        return self._spec

    def ramp_surface_point(
        self, *, contact_coordinate: float, axial_position: float
    ) -> tuple[float, float]:
        """Return the physical ramp surface point ``(x, r)``."""

        self._require_axial_position(axial_position)
        profile = self._spec.ramp_profile
        tolerance = self._spec.coordinate_tolerance
        if not (
            profile.x_min - tolerance <= contact_coordinate <= profile.x_max + tolerance
        ):
            raise ValueError(
                "contact_coordinate is outside the physical ramp profile "
                f"[{profile.x_min}, {profile.x_max}]."
            )
        xi = min(profile.x_max, max(profile.x_min, float(contact_coordinate)))
        ramp = profile.evaluate(xi)
        return (
            self._spec.ramp_reference_axial_position
            + axial_position
            + self._spec.ramp_axial_direction * xi,
            self._spec.ramp_reference_radius + ramp.value,
        )

    def contact_candidates(
        self, axial_position: float
    ) -> tuple[PivotedRollerContactCandidate, ...]:
        """Return every instantaneous mathematical contact configuration.

        Smooth-segment contacts come from the usual radius-offset curve. C0
        junctions are handled separately as physical corner contacts: the
        roller centre lies exactly one roller radius from the corner and exactly
        one arm length from the pivot.

        Candidate multiplicity is not itself a double-contact failure.
        """

        self._require_axial_position(axial_position)
        candidates: list[PivotedRollerContactCandidate] = []

        for xi in self._contact_roots(axial_position):
            curve = self._offset_curve(
                xi=xi,
                axial_position=axial_position,
            )
            contact_x, contact_r = self.ramp_surface_point(
                contact_coordinate=xi,
                axial_position=axial_position,
            )
            vx = curve.x - self._spec.pivot_axial_position
            vr = curve.radius - self._spec.pivot_radius
            candidates.append(
                PivotedRollerContactCandidate(
                    contact_coordinate=xi,
                    contact_axial_position=contact_x,
                    contact_radius=contact_r,
                    roller_center_axial_position=curve.x,
                    roller_center_radius=curve.radius,
                    angle=atan2(vr, vx),
                    corner_contact=False,
                )
            )

        candidates.extend(self._corner_contact_candidates(axial_position))

        candidates.sort(key=lambda candidate: candidate.angle)
        unique: list[PivotedRollerContactCandidate] = []
        tolerance = self._spec.coordinate_tolerance
        for candidate in candidates:
            duplicate = False
            for other in unique:
                center_distance = sqrt(
                    (
                        candidate.roller_center_axial_position
                        - other.roller_center_axial_position
                    )
                    ** 2
                    + (candidate.roller_center_radius - other.roller_center_radius) ** 2
                )
                if center_distance <= 8.0 * tolerance:
                    duplicate = True
                    break
            if not duplicate:
                unique.append(candidate)
        return tuple(unique)

    def evaluate(self, axial_position: float) -> PivotedRollerContactSample:
        """Evaluate a position only when its contact configuration is unique."""

        candidates = self.contact_candidates(axial_position)
        if not candidates:
            raise ValueError(
                "No roller/ramp contact exists at local axial position "
                f"{axial_position:.12g}."
            )
        if len(candidates) != 1:
            raise ValueError(
                "Multiple mathematical arm configurations touch the ramp at "
                f"local axial position {axial_position:.12g}; use branch "
                "selection rather than the unique-contact helper."
            )
        return self._evaluate_candidate(
            axial_position=axial_position,
            candidate=candidates[0],
        )

    def trace_contact_branch(
        self,
        positions: np.ndarray,
        *,
        require_complete: bool = True,
    ) -> tuple[PivotedRollerContactSample, ...]:
        """Select the smallest-q initial contact and follow it continuously."""

        points = np.asarray(positions, dtype=float)
        if points.ndim != 1 or points.size == 0:
            raise ValueError("positions must be a non-empty one-dimensional array.")
        if not np.all(np.isfinite(points)):
            raise ValueError("positions must contain only finite values.")
        if np.any(np.diff(points) <= 0.0):
            raise ValueError("positions must be strictly increasing.")

        tolerance = self._spec.coordinate_tolerance
        if abs(float(points[0]) - self._spec.axial_position_min) > tolerance:
            raise ValueError(
                "Contact-branch tracing must begin at axial_position_min so "
                "the assembled branch is selected unambiguously."
            )
        if float(points[-1]) > self._spec.axial_position_max + tolerance:
            raise ValueError("Branch-trace positions exceed axial_position_max.")

        initial_candidates = self.contact_candidates(float(points[0]))
        if not initial_candidates:
            if require_complete:
                raise ValueError(
                    "No roller/ramp contact exists at the beginning of the "
                    "fixed-pivot operating interval."
                )
            return ()

        initial_candidate = min(
            initial_candidates,
            key=lambda candidate: candidate.angle,
        )
        initial = self._evaluate_candidate(
            axial_position=float(points[0]),
            candidate=initial_candidate,
        )
        self._validate_noninterference(
            axial_position=float(points[0]),
            sample=initial,
        )

        selected: list[PivotedRollerContactSample] = [initial]
        previous_position = float(points[0])
        previous_angle = initial.angle
        previous_coordinate = initial.contact_coordinate
        previous_sample = initial

        for raw_position in points[1:]:
            position = float(raw_position)
            candidates = self.contact_candidates(position)
            if not candidates:
                if require_complete:
                    raise ValueError(
                        "The selected fixed-pivot contact branch cannot be "
                        f"continued to local axial position {position:.12g}: "
                        "no mathematical contact exists."
                    )
                break

            delta = position - previous_position
            predicted_angle = (
                previous_angle
                + previous_sample.angle_gradient * delta
                + 0.5 * previous_sample.angle_curvature * delta**2
            )

            ranked: list[
                tuple[
                    float,
                    float,
                    float,
                    PivotedRollerContactCandidate,
                ]
            ] = []
            for candidate in candidates:
                unwrapped = candidate.angle + 2.0 * pi * round(
                    (predicted_angle - candidate.angle) / (2.0 * pi)
                )
                ranked.append(
                    (
                        abs(unwrapped - predicted_angle),
                        abs(candidate.contact_coordinate - previous_coordinate),
                        unwrapped,
                        candidate,
                    )
                )
            ranked.sort(key=lambda item: (item[0], item[1]))
            angle_error, _coordinate_error, unwrapped, candidate = ranked[0]

            expected_motion = abs(previous_sample.angle_gradient * delta) + 0.5 * abs(
                previous_sample.angle_curvature * delta**2
            )
            continuity_tolerance = max(0.05, 16.0 * expected_motion)
            if angle_error > continuity_tolerance:
                if require_complete:
                    raise ValueError(
                        "The selected fixed-pivot contact branch cannot be "
                        "continued without jumping to a disconnected "
                        f"mathematical solution near local axial position "
                        f"{position:.12g}."
                    )
                break

            try:
                sample = self._evaluate_candidate(
                    axial_position=position,
                    candidate=candidate,
                )
                self._validate_noninterference(
                    axial_position=position,
                    sample=sample,
                )
            except ValueError:
                if require_complete:
                    raise
                break

            sample = PivotedRollerContactSample(
                contact_coordinate=sample.contact_coordinate,
                roller_center_axial_position=sample.roller_center_axial_position,
                roller_center_radius=sample.roller_center_radius,
                angle=unwrapped,
                angle_gradient=sample.angle_gradient,
                angle_curvature=sample.angle_curvature,
                contact_residual=sample.contact_residual,
                offset_regular_factor=sample.offset_regular_factor,
            )
            selected.append(sample)
            previous_position = position
            previous_angle = unwrapped
            previous_coordinate = sample.contact_coordinate
            previous_sample = sample

        return tuple(selected)

    def validate_operating_interval(self) -> tuple[PivotedRollerContactSample, ...]:
        """Validate the history-selected branch over the active interval."""

        positions = np.linspace(
            self._spec.axial_position_min,
            self._spec.axial_position_max,
            self._spec.validation_positions,
        )
        return self.trace_contact_branch(positions, require_complete=True)

    def audit_operating_interval(
        self,
        *,
        sample_count: int | None = None,
        require_profile_c3: bool = True,
    ) -> FixedPivotValidationReport:
        """Audit geometry and selected branch across declared travel.

        Multiple instantaneous mathematical arm configurations are allowed.
        The physical branch is still the smallest-q initial configuration
        followed continuously through travel.
        """

        count = (
            max(257, self._spec.validation_positions)
            if sample_count is None
            else sample_count
        )
        if isinstance(count, bool) or not isinstance(count, int) or count < 9:
            raise ValueError("sample_count must be an integer of at least 9.")

        findings: list[FixedPivotValidationFinding] = []
        profile = self._spec.ramp_profile

        continuity_method = getattr(
            profile,
            "junction_continuity",
            None,
        )
        if require_profile_c3 and callable(continuity_method):
            for junction in continuity_method():
                if not junction.is_continuous(order=3):
                    findings.append(
                        FixedPivotValidationFinding(
                            severity="error",
                            code="profile.not_c3",
                            message=(
                                "Acceleration-level fixed-pivot dynamics "
                                "require a C3 physical ramp; a derivative "
                                "jump exists at profile coordinate "
                                f"{junction.coordinate:.12g} m."
                            ),
                            contact_coordinate=(junction.coordinate),
                        )
                    )

        profile_positions = np.linspace(
            profile.x_min,
            profile.x_max,
            count,
        )
        for coordinate in profile_positions:
            profile_sample = profile.evaluate(float(coordinate))
            if profile_sample.third_derivative is None:
                findings.append(
                    FixedPivotValidationFinding(
                        severity="error",
                        code="profile.third_derivative_missing",
                        message=(
                            "Physical ramp does not provide the third "
                            "derivative required by the exact q'' "
                            "calculation."
                        ),
                        contact_coordinate=float(coordinate),
                    )
                )
                break

        positions = np.linspace(
            self._spec.axial_position_min,
            self._spec.axial_position_max,
            count,
        )
        try:
            samples = self.trace_contact_branch(
                positions,
                require_complete=True,
            )
        except ValueError as error:
            findings.append(
                FixedPivotValidationFinding(
                    severity="error",
                    code="contact.branch_invalid",
                    message=str(error),
                )
            )
            samples = self.trace_contact_branch(
                positions,
                require_complete=False,
            )

        traced_count = len(samples)
        if traced_count != count:
            failed_position = float(positions[min(traced_count, count - 1)])
            findings.append(
                FixedPivotValidationFinding(
                    severity="error",
                    code="contact.branch_incomplete",
                    message=(
                        "Selected smallest-q branch does not remain "
                        "admissible across the entire declared operating "
                        "interval."
                    ),
                    axial_position=failed_position,
                )
            )

        minimum_gradient: float | None = None
        maximum_curvature: float | None = None
        maximum_arm_error: float | None = None
        minimum_regular: float | None = None
        minimum_endpoint_margin: float | None = None
        maximum_candidates = 0

        arm_error_limit = max(
            64.0 * self._spec.coordinate_tolerance,
            1.0e-10,
        )
        near_endpoint_limit = max(
            64.0 * self._spec.coordinate_tolerance,
            0.01 * (profile.x_max - profile.x_min),
        )

        for index, sample in enumerate(samples):
            axial_position = float(positions[index])
            candidate_count = len(self.contact_candidates(axial_position))
            maximum_candidates = max(
                maximum_candidates,
                candidate_count,
            )

            arm_length = hypot(
                sample.roller_center_axial_position - self._spec.pivot_axial_position,
                sample.roller_center_radius - self._spec.pivot_radius,
            )
            arm_error = abs(arm_length - self._spec.arm_length)
            maximum_arm_error = (
                arm_error
                if maximum_arm_error is None
                else max(maximum_arm_error, arm_error)
            )

            gradient = sample.angle_gradient
            minimum_gradient = (
                gradient
                if minimum_gradient is None
                else min(minimum_gradient, gradient)
            )

            curvature = abs(sample.angle_curvature)
            maximum_curvature = (
                curvature
                if maximum_curvature is None
                else max(maximum_curvature, curvature)
            )

            regular = abs(sample.offset_regular_factor)
            minimum_regular = (
                regular if minimum_regular is None else min(minimum_regular, regular)
            )

            endpoint_margin = min(
                sample.contact_coordinate - profile.x_min,
                profile.x_max - sample.contact_coordinate,
            )
            minimum_endpoint_margin = (
                endpoint_margin
                if minimum_endpoint_margin is None
                else min(
                    minimum_endpoint_margin,
                    endpoint_margin,
                )
            )

            if arm_error > arm_error_limit:
                findings.append(
                    FixedPivotValidationFinding(
                        severity="error",
                        code="geometry.arm_length_residual",
                        message=(
                            "Selected roller centre violates the rigid "
                            "pivot-to-roller length by "
                            f"{arm_error:.6g} m."
                        ),
                        axial_position=axial_position,
                        contact_coordinate=(sample.contact_coordinate),
                    )
                )
                break

        if minimum_gradient is not None and (
            not isfinite(minimum_gradient) or minimum_gradient <= 0.0
        ):
            findings.append(
                FixedPivotValidationFinding(
                    severity="error",
                    code="kinematics.nonpositive_motion_ratio",
                    message=(
                        "Selected branch reaches a non-finite or " "non-positive dq/dx."
                    ),
                )
            )

        if maximum_curvature is not None and not isfinite(maximum_curvature):
            findings.append(
                FixedPivotValidationFinding(
                    severity="error",
                    code="kinematics.nonfinite_curvature",
                    message="Selected branch produces a non-finite q''.",
                )
            )

        if minimum_regular is not None and minimum_regular < 0.05:
            findings.append(
                FixedPivotValidationFinding(
                    severity="warning",
                    code="roller_offset.near_singular",
                    message=(
                        "Roller-centre offset curve approaches its "
                        "curvature singularity."
                    ),
                )
            )

        if (
            minimum_endpoint_margin is not None
            and minimum_endpoint_margin < near_endpoint_limit
        ):
            findings.append(
                FixedPivotValidationFinding(
                    severity="warning",
                    code="ramp.endpoint_margin_small",
                    message=(
                        "Selected contact approaches a finite ramp "
                        "endpoint; confirm physical manufacturing margin."
                    ),
                )
            )

        if maximum_candidates > 1:
            findings.append(
                FixedPivotValidationFinding(
                    severity="info",
                    code="contact.alternate_configurations",
                    message=(
                        "More than one instantaneous mathematical arm "
                        "configuration exists at some positions. This is "
                        "allowed; construction follows the continuous "
                        "branch selected by the smallest initial q."
                    ),
                )
            )

        return FixedPivotValidationReport(
            findings=tuple(findings),
            requested_positions=count,
            traced_positions=traced_count,
            minimum_angle_gradient=minimum_gradient,
            maximum_absolute_angle_curvature=(maximum_curvature),
            maximum_arm_length_error=maximum_arm_error,
            minimum_absolute_offset_regular_factor=(minimum_regular),
            minimum_ramp_endpoint_margin=(minimum_endpoint_margin),
            maximum_mathematical_candidates=(maximum_candidates),
        )

    def _evaluate_candidate(
        self,
        *,
        axial_position: float,
        candidate: PivotedRollerContactCandidate,
    ) -> PivotedRollerContactSample:
        if candidate.corner_contact:
            return self._evaluate_corner_candidate(
                axial_position=axial_position,
                candidate=candidate,
            )
        return self._evaluate_contact_root(
            axial_position=axial_position,
            contact_coordinate=candidate.contact_coordinate,
        )

    def _evaluate_corner_candidate(
        self,
        *,
        axial_position: float,
        candidate: PivotedRollerContactCandidate,
    ) -> PivotedRollerContactSample:
        """Evaluate exact q, q', q'' while the roller rides a ramp corner."""

        px = self._spec.pivot_axial_position
        pr = self._spec.pivot_radius
        length = self._spec.arm_length

        jx = candidate.contact_axial_position
        jr = candidate.contact_radius
        dx = jx - px
        dr = jr - pr
        q = candidate.angle

        g_q = 2.0 * length * (dx * sin(q) - dr * cos(q))
        scale = max(1.0, length)
        if abs(g_q) <= self._spec.root_residual_tolerance / scale:
            raise ValueError(
                "The selected corner-contact branch reaches a fold or "
                f"dead-centre at local axial position {axial_position:.12g}."
            )

        g_x = 2.0 * dx - 2.0 * length * cos(q)
        angle_gradient = -g_x / g_q

        g_xx = 2.0
        g_x_q = 2.0 * length * sin(q)
        g_q_q = 2.0 * length * (dx * cos(q) + dr * sin(q))
        angle_curvature = (
            -(g_xx + 2.0 * g_x_q * angle_gradient + g_q_q * angle_gradient**2) / g_q
        )

        if not isfinite(angle_gradient) or angle_gradient <= 0.0:
            raise ValueError(
                "The selected corner-contact branch does not produce finite, "
                "positive outward rotation per unit local closure."
            )
        if not isfinite(angle_curvature):
            raise ValueError("Corner-contact angle curvature is not finite.")

        vx = candidate.roller_center_axial_position - px
        vr = candidate.roller_center_radius - pr
        residual = vx * vx + vr * vr - length**2

        return PivotedRollerContactSample(
            contact_coordinate=candidate.contact_coordinate,
            roller_center_axial_position=candidate.roller_center_axial_position,
            roller_center_radius=candidate.roller_center_radius,
            angle=q,
            angle_gradient=angle_gradient,
            angle_curvature=angle_curvature,
            contact_residual=residual,
            offset_regular_factor=1.0,
        )

    def _evaluate_contact_root(
        self,
        *,
        axial_position: float,
        contact_coordinate: float,
    ) -> PivotedRollerContactSample:
        """Evaluate one specified smooth-segment contact root."""

        xi = float(contact_coordinate)
        curve = self._offset_curve(xi=xi, axial_position=axial_position)
        vx = curve.x - self._spec.pivot_axial_position
        vr = curve.radius - self._spec.pivot_radius
        g = vx * vx + vr * vr - self._spec.arm_length**2

        g_x = 2.0 * vx
        g_xx = 2.0
        g_x_xi = 2.0 * curve.dx_dxi
        g_xi = 2.0 * (vx * curve.dx_dxi + vr * curve.dr_dxi)
        g_xi_xi = 2.0 * (
            curve.dx_dxi**2
            + curve.dr_dxi**2
            + vx * curve.d2x_dxi2
            + vr * curve.d2r_dxi2
        )
        scale = max(1.0, self._spec.arm_length)
        if abs(g_xi) <= self._spec.root_residual_tolerance / scale:
            raise ValueError(
                "The selected roller/ramp branch reaches a fold or "
                f"dead-centre at local axial position {axial_position:.12g}."
            )

        xi_gradient = -g_x / g_xi
        xi_curvature = (
            -(g_xx + 2.0 * g_x_xi * xi_gradient + g_xi_xi * xi_gradient**2) / g_xi
        )

        center_x_gradient = 1.0 + curve.dx_dxi * xi_gradient
        center_r_gradient = curve.dr_dxi * xi_gradient
        center_x_curvature = (
            curve.d2x_dxi2 * xi_gradient**2 + curve.dx_dxi * xi_curvature
        )
        center_r_curvature = (
            curve.d2r_dxi2 * xi_gradient**2 + curve.dr_dxi * xi_curvature
        )

        arm_length_squared = self._spec.arm_length**2
        angle = atan2(vr, vx)
        angle_gradient = (
            vx * center_r_gradient - vr * center_x_gradient
        ) / arm_length_squared
        angle_curvature = (
            vx * center_r_curvature - vr * center_x_curvature
        ) / arm_length_squared
        if not isfinite(angle_gradient) or angle_gradient <= 0.0:
            raise ValueError(
                "The selected roller/ramp branch does not produce finite, "
                "positive outward rotation per unit local closure."
            )
        if not isfinite(angle_curvature):
            raise ValueError("The roller/ramp angle curvature is not finite.")

        return PivotedRollerContactSample(
            contact_coordinate=xi,
            roller_center_axial_position=curve.x,
            roller_center_radius=curve.radius,
            angle=angle,
            angle_gradient=angle_gradient,
            angle_curvature=angle_curvature,
            contact_residual=g,
            offset_regular_factor=curve.offset_regular_factor,
        )

    def _corner_contact_candidates(
        self,
        axial_position: float,
    ) -> tuple[PivotedRollerContactCandidate, ...]:
        """Return exact finite-roller contacts at C0 PiecewiseRamp junctions."""

        segments = getattr(self._spec.ramp_profile, "segments", ())
        if len(segments) < 2:
            return ()

        direction = float(self._spec.ramp_axial_direction)
        sign = float(self._spec.roller_side_sign)
        px = self._spec.pivot_axial_position
        pr = self._spec.pivot_radius
        length = self._spec.arm_length
        roller = self._spec.roller_radius
        tolerance = self._spec.coordinate_tolerance

        def normal_for_slope(slope: float) -> tuple[float, float]:
            norm = sqrt(1.0 + slope * slope)
            return (
                -sign * slope / norm,
                sign * direction / norm,
            )

        def wrapped_delta(start: float, end: float) -> float:
            return atan2(sin(end - start), cos(end - start))

        candidates: list[PivotedRollerContactCandidate] = []
        xi = 0.0

        for index in range(len(segments) - 1):
            left = segments[index]
            right = segments[index + 1]
            xi += left.length

            left_sample = left.evaluate_local(left.length)
            right_sample = right.evaluate_local(0.0)
            left_normal = normal_for_slope(left_sample.first_derivative)
            right_normal = normal_for_slope(right_sample.first_derivative)

            left_angle = atan2(left_normal[1], left_normal[0])
            right_angle = atan2(right_normal[1], right_normal[0])
            normal_span = wrapped_delta(left_angle, right_angle)

            if abs(normal_span) <= 64.0 * np.finfo(float).eps:
                continue

            jx, jr = self.ramp_surface_point(
                contact_coordinate=xi,
                axial_position=axial_position,
            )
            dx = jx - px
            dr = jr - pr
            distance = sqrt(dx * dx + dr * dr)

            if (
                distance > length + roller + tolerance
                or distance < abs(length - roller) - tolerance
                or distance <= tolerance
            ):
                continue

            along = (length**2 - roller**2 + distance**2) / (2.0 * distance)
            height_squared = length**2 - along**2
            h_tolerance = tolerance * max(length, roller, distance)
            if height_squared < -h_tolerance:
                continue
            height = sqrt(max(0.0, height_squared))

            ux = dx / distance
            ur = dr / distance
            bx = px + along * ux
            br = pr + along * ur

            centers = (
                (bx - height * ur, br + height * ux),
                (bx + height * ur, br - height * ux),
            )
            angular_tolerance = 1.0e-9

            for cx, cr in centers:
                nx = (cx - jx) / roller
                nr = (cr - jr) / roller
                normal_angle = atan2(nr, nx)
                candidate_delta = wrapped_delta(left_angle, normal_angle)

                if normal_span >= 0.0:
                    inside = (
                        -angular_tolerance
                        <= candidate_delta
                        <= normal_span + angular_tolerance
                    )
                else:
                    inside = (
                        normal_span - angular_tolerance
                        <= candidate_delta
                        <= angular_tolerance
                    )
                if not inside:
                    continue

                candidates.append(
                    PivotedRollerContactCandidate(
                        contact_coordinate=xi,
                        contact_axial_position=jx,
                        contact_radius=jr,
                        roller_center_axial_position=cx,
                        roller_center_radius=cr,
                        angle=atan2(cr - pr, cx - px),
                        corner_contact=True,
                    )
                )

        return tuple(candidates)

    def _require_axial_position(self, axial_position: float) -> None:
        if not isfinite(axial_position):
            raise ValueError("axial_position must be finite.")
        tolerance = self._spec.coordinate_tolerance
        if not (
            self._spec.axial_position_min - tolerance
            <= axial_position
            <= self._spec.axial_position_max + tolerance
        ):
            raise ValueError(
                f"axial_position={axial_position} is outside the fixed-pivot "
                "flyweight map interval "
                f"[{self._spec.axial_position_min}, {self._spec.axial_position_max}]."
            )

    def _contact_roots(self, axial_position: float) -> tuple[float, ...]:
        xi_values = np.linspace(
            self._spec.ramp_profile.x_min,
            self._spec.ramp_profile.x_max,
            self._spec.root_scan_points,
        )
        residuals = np.asarray(
            [self._contact_residual(float(xi), axial_position) for xi in xi_values],
            dtype=float,
        )
        roots: list[float] = []
        tolerance = self._spec.root_residual_tolerance

        for xi, residual in zip(xi_values, residuals, strict=True):
            if abs(float(residual)) <= tolerance:
                roots.append(float(xi))

        for index in range(len(xi_values) - 1):
            left_residual = float(residuals[index])
            right_residual = float(residuals[index + 1])
            if left_residual * right_residual >= 0.0:
                continue

            root = float(
                brentq(
                    lambda xi: self._contact_residual(xi, axial_position),
                    float(xi_values[index]),
                    float(xi_values[index + 1]),
                    xtol=min(1.0e-13, self._spec.coordinate_tolerance / 10.0),
                    rtol=1.0e-13,
                )
            )

            # Brent assumes continuity. A PiecewiseRamp may only be C0, so the
            # roller-centre offset curve can jump at a slope discontinuity.
            # A sign change across that jump is not a root. Verify the returned
            # point actually satisfies the rigid-arm circle before accepting it.
            if abs(self._contact_residual(root, axial_position)) <= 8.0 * tolerance:
                roots.append(root)

        roots.sort()
        unique: list[float] = []
        for root in roots:
            if not unique or abs(root - unique[-1]) > self._spec.coordinate_tolerance:
                unique.append(root)
        return tuple(unique)

    def _contact_residual(self, xi: float, axial_position: float) -> float:
        curve = self._offset_curve(xi=xi, axial_position=axial_position)
        dx = curve.x - self._spec.pivot_axial_position
        dr = curve.radius - self._spec.pivot_radius
        return dx * dx + dr * dr - self._spec.arm_length**2

    def _offset_curve(self, *, xi: float, axial_position: float) -> "_OffsetCurve":
        profile = self._spec.ramp_profile.evaluate(xi)
        slope = profile.first_derivative
        second = profile.second_derivative
        third = profile.third_derivative
        if third is None:
            raise ValueError(
                "The physical roller ramp must provide a third derivative so "
                "the fixed-pivot map can evaluate q'' analytically."
            )

        # The scalar profile is parameterized by positive profile coordinate
        # xi, while its physical axial direction may be either +x or -x.
        # For the Baja convention ramp_axial_direction=-1: positive xi walks
        # from Point A toward the pivot while profile.value increases radially
        # outward.
        direction = float(self._spec.ramp_axial_direction)
        norm = sqrt(1.0 + slope * slope)
        sign = float(self._spec.roller_side_sign)

        # Unit normal to tangent (direction, slope), with roller_side_sign
        # selecting which side of the physical ramp carries the roller.
        normal_x = -sign * slope / norm
        normal_r = sign * direction / norm
        normal_x_gradient = -sign * second / norm**3
        normal_r_gradient = -sign * direction * slope * second / norm**3
        normal_x_curvature = -sign * (
            third / norm**3 - 3.0 * slope * second**2 / norm**5
        )
        normal_r_curvature = (
            -sign
            * direction
            * (
                (second**2 + slope * third) / norm**3
                - 3.0 * slope**2 * second**2 / norm**5
            )
        )

        roller = self._spec.roller_radius
        signed_curvature = sign * direction * second / norm**3
        regular_factor = 1.0 - roller * signed_curvature
        if abs(regular_factor) <= 64.0 * np.finfo(float).eps:
            raise ValueError("The roller-center offset curve is singular.")

        ramp_x, ramp_r = self.ramp_surface_point(
            contact_coordinate=xi,
            axial_position=axial_position,
        )
        return _OffsetCurve(
            x=ramp_x + roller * normal_x,
            radius=ramp_r + roller * normal_r,
            dx_dxi=direction + roller * normal_x_gradient,
            dr_dxi=slope + roller * normal_r_gradient,
            d2x_dxi2=roller * normal_x_curvature,
            d2r_dxi2=second + roller * normal_r_curvature,
            offset_regular_factor=regular_factor,
        )

    def _validate_noninterference(
        self,
        *,
        axial_position: float,
        sample: PivotedRollerContactSample,
    ) -> None:
        """Reject penetration or a true second contact of the selected roller.

        This check is intentionally performed *after* contact-branch selection.
        Multiple arm orientations may solve the instantaneous geometry.  The
        invalid case here is different: one already-selected roller pose
        touching or penetrating a second portion of the physical ramp.
        """

        profile = self._spec.ramp_profile
        grid = np.linspace(profile.x_min, profile.x_max, self._spec.root_scan_points)
        center_x = sample.roller_center_axial_position
        center_r = sample.roller_center_radius
        roller_squared = self._spec.roller_radius**2

        def clearance_squared(xi: float) -> float:
            ramp_x, ramp_r = self.ramp_surface_point(
                contact_coordinate=float(xi),
                axial_position=axial_position,
            )
            dx = center_x - ramp_x
            dr = center_r - ramp_r
            return dx * dx + dr * dr - roller_squared

        values = np.asarray([clearance_squared(float(xi)) for xi in grid])
        minima: list[tuple[float, float]] = [
            (
                sample.contact_coordinate,
                clearance_squared(sample.contact_coordinate),
            )
        ]
        for index in range(1, len(grid) - 1):
            if values[index] > values[index - 1] or values[index] > values[index + 1]:
                continue
            result = minimize_scalar(
                clearance_squared,
                bounds=(float(grid[index - 1]), float(grid[index + 1])),
                method="bounded",
                options={"xatol": self._spec.coordinate_tolerance / 10.0},
            )
            minima.append((float(result.x), float(result.fun)))
        minima.extend(
            (
                (float(grid[0]), float(values[0])),
                (float(grid[-1]), float(values[-1])),
            )
        )

        clearance_tolerance = max(
            self._spec.root_residual_tolerance,
            self._spec.coordinate_tolerance * self._spec.roller_radius,
        )
        for coordinate, clearance in minima:
            if clearance < -clearance_tolerance:
                raise ValueError(
                    "The selected roller configuration penetrates another "
                    "portion of the physical ramp at local axial position "
                    f"{axial_position:.12g}."
                )
            if (
                abs(clearance) <= clearance_tolerance
                and abs(coordinate - sample.contact_coordinate)
                > 8.0 * self._spec.coordinate_tolerance
            ):
                raise ValueError(
                    "The selected roller configuration has a second "
                    "simultaneous physical ramp contact at local axial "
                    f"position {axial_position:.12g}."
                )


@dataclass(frozen=True, slots=True)
class _OffsetCurve:
    x: float
    radius: float
    dx_dxi: float
    dr_dxi: float
    d2x_dxi2: float
    d2r_dxi2: float
    offset_regular_factor: float


class PivotedRollerFollowerFlyweightMap:
    """Runtime ``q, J, I`` map compiled from the selected contact branch.

    Construction chooses the smallest-q mathematical contact at the beginning
    of travel and follows that branch continuously across the operating
    interval.  A clamped cubic spline then provides the cheap C2 runtime angle
    map.  Shaft inertia and its derivative continue to come from the physical
    mass moments rather than an independently fitted law.
    """

    def __init__(
        self,
        *,
        geometry_spec: PivotedRollerFollowerGeometrySpec,
        mass_geometry: FlyweightMassGeometry,
        compilation_points: int = 257,
    ) -> None:
        if not isinstance(mass_geometry, FlyweightMassGeometry):
            raise TypeError("mass_geometry must be a FlyweightMassGeometry.")
        if (
            isinstance(compilation_points, bool)
            or not isinstance(compilation_points, int)
            or compilation_points < 9
        ):
            raise ValueError("compilation_points must be an integer of at least 9.")

        self._geometry = PivotedRollerFollowerGeometry(geometry_spec)
        self._mass_geometry = mass_geometry
        self._compilation_points = compilation_points

        # A coarser independent construction check catches branch loss and
        # same-pose second contact before fitting the runtime spline.
        self._validation_report = self._geometry.audit_operating_interval(
            sample_count=max(257, 2 * compilation_points - 1),
            require_profile_c3=True,
        )
        self._validation_report.require_valid()

        positions = np.linspace(
            geometry_spec.axial_position_min,
            geometry_spec.axial_position_max,
            compilation_points,
        )
        exact = self._geometry.trace_contact_branch(
            positions,
            require_complete=True,
        )
        if len(exact) != compilation_points:
            raise RuntimeError(
                "Fixed-pivot branch compilation returned an incomplete trace."
            )

        angles = np.asarray([item.angle for item in exact], dtype=float)
        self._angle_spline = CubicSpline(
            positions,
            angles,
            bc_type=(
                (1, exact[0].angle_gradient),
                (1, exact[-1].angle_gradient),
            ),
        )

        validation_positions = np.linspace(
            geometry_spec.axial_position_min,
            geometry_spec.axial_position_max,
            2 * compilation_points - 1,
        )
        gradients = np.asarray(
            self._angle_spline(validation_positions, 1),
            dtype=float,
        )
        if not np.all(np.isfinite(gradients)) or np.min(gradients) <= 0.0:
            raise ValueError(
                "The compiled fixed-pivot flyweight map reverses or reaches a "
                "singular motion ratio."
            )

    @property
    def validation_report(self) -> FixedPivotValidationReport:
        """Return the construction audit used to admit this map."""

        return self._validation_report

    @property
    def geometry_spec(self) -> PivotedRollerFollowerGeometrySpec:
        return self._geometry.spec

    @property
    def mass_geometry(self) -> FlyweightMassGeometry:
        return self._mass_geometry

    @property
    def compilation_points(self) -> int:
        return self._compilation_points

    @property
    def axial_position_min(self) -> float:
        return self.geometry_spec.axial_position_min

    @property
    def axial_position_max(self) -> float:
        return self.geometry_spec.axial_position_max

    def evaluate(self, axial_position: float) -> FixedPivotFlyweightSample:
        self._geometry._require_axial_position(axial_position)
        angle = float(self._angle_spline(axial_position))
        angle_gradient = float(self._angle_spline(axial_position, 1))
        angle_curvature = float(self._angle_spline(axial_position, 2))
        return self._compose_sample(
            angle=angle,
            angle_gradient=angle_gradient,
            angle_curvature=angle_curvature,
        )

    def evaluate_exact(self, axial_position: float) -> FixedPivotFlyweightSample:
        """Evaluate the exact contact belonging to the compiled branch."""

        contact = self._selected_exact_contact(axial_position)
        return self._compose_sample(
            angle=contact.angle,
            angle_gradient=contact.angle_gradient,
            angle_curvature=contact.angle_curvature,
        )

    def contact_at(self, axial_position: float) -> PivotedRollerContactSample:
        """Return the exact contact belonging to the compiled branch."""

        return self._selected_exact_contact(axial_position)

    def _selected_exact_contact(
        self,
        axial_position: float,
    ) -> PivotedRollerContactSample:
        self._geometry._require_axial_position(axial_position)
        reference = float(self._angle_spline(axial_position))
        candidates = self._geometry.contact_candidates(axial_position)
        if not candidates:
            raise RuntimeError(
                "Compiled fixed-pivot branch has no exact contact at "
                f"axial_position={axial_position:.12g}."
            )

        ranked: list[tuple[float, float, PivotedRollerContactCandidate]] = []
        for candidate in candidates:
            unwrapped = candidate.angle + 2.0 * pi * round(
                (reference - candidate.angle) / (2.0 * pi)
            )
            ranked.append(
                (
                    abs(unwrapped - reference),
                    unwrapped,
                    candidate,
                )
            )
        ranked.sort(key=lambda item: item[0])
        _error, unwrapped, candidate = ranked[0]

        sample = self._geometry._evaluate_candidate(
            axial_position=axial_position,
            candidate=candidate,
        )
        self._geometry._validate_noninterference(
            axial_position=axial_position,
            sample=sample,
        )
        return PivotedRollerContactSample(
            contact_coordinate=sample.contact_coordinate,
            roller_center_axial_position=sample.roller_center_axial_position,
            roller_center_radius=sample.roller_center_radius,
            angle=unwrapped,
            angle_gradient=sample.angle_gradient,
            angle_curvature=sample.angle_curvature,
            contact_residual=sample.contact_residual,
            offset_regular_factor=sample.offset_regular_factor,
        )

    def _compose_sample(
        self,
        *,
        angle: float,
        angle_gradient: float,
        angle_curvature: float,
    ) -> FixedPivotFlyweightSample:
        pivot_radius = self.geometry_spec.pivot_radius
        shaft_inertia = self._mass_geometry.shaft_inertia(
            angle=angle,
            pivot_radius=pivot_radius,
        )
        shaft_inertia_gradient = (
            self._mass_geometry.shaft_inertia_angle_gradient(
                angle=angle,
                pivot_radius=pivot_radius,
            )
            * angle_gradient
        )
        return FixedPivotFlyweightSample(
            angle=angle,
            angle_gradient=angle_gradient,
            angle_curvature=angle_curvature,
            shaft_inertia=shaft_inertia,
            shaft_inertia_gradient=shaft_inertia_gradient,
            pivot_inertia=self._mass_geometry.pivot_inertia,
        )
