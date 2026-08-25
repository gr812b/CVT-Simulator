"""Fixed-pivot flyweight maps for a translating roller-ramp follower.

This module implements the mechanism constructed in the formulation appendix:
the pivot is fixed to the pulley, the ramp translates with the movable sheave,
and a rigid roller arm supplies the single relative coordinate ``q_f(x)``.
It deliberately does not claim to be a universal flyweight abstraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, isfinite, sin, sqrt
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
            raise ValueError("product_moment_uv is inconsistent with the second moments.")

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
            mass_per_flyweight=(
                arm_mass_per_flyweight + end_mass_per_flyweight
            ),
            first_moment_u=first_u,
            first_moment_v=0.0,
            second_moment_u=second_u,
            second_moment_v=0.0,
            product_moment_uv=0.0,
            second_moment_z=second_moment_z_per_flyweight,
        )

    @property
    def pivot_inertia(self) -> float:
        """Return total ``I_f`` about the circumferential pivot axes."""

        return self.number_of_flyweights * (
            self.second_moment_u + self.second_moment_v
        )

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
            + 2.0
            * (self.second_moment_u - self.second_moment_v)
            * sine
            * cosine
            + 2.0
            * self.product_moment_uv
            * (cosine**2 - sine**2)
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


class PivotedRollerFollowerGeometry:
    """Exact circle/offset-ramp contact solve from the formulation appendix."""

    def __init__(self, spec: PivotedRollerFollowerGeometrySpec) -> None:
        if not isinstance(spec, PivotedRollerFollowerGeometrySpec):
            raise TypeError("spec must be a PivotedRollerFollowerGeometrySpec.")
        self._spec = spec

    @property
    def spec(self) -> PivotedRollerFollowerGeometrySpec:
        return self._spec

    def evaluate(self, axial_position: float) -> PivotedRollerContactSample:
        """Solve the unique regular contact at one movable-ramp position."""

        self._require_axial_position(axial_position)
        roots = self._contact_roots(axial_position)
        if not roots:
            raise ValueError(
                "No roller/ramp contact exists at local axial position "
                f"{axial_position:.12g}."
            )
        if len(roots) != 1:
            raise ValueError(
                "The roller touches the ramp at multiple geometric points at "
                f"local axial position {axial_position:.12g}."
            )

        xi = roots[0]
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
                "The roller/ramp branch reaches a fold or dead-centre "
                f"at local axial position {axial_position:.12g}."
            )

        xi_gradient = -g_x / g_xi
        xi_curvature = -(
            g_xx
            + 2.0 * g_x_xi * xi_gradient
            + g_xi_xi * xi_gradient**2
        ) / g_xi

        center_x_gradient = 1.0 + curve.dx_dxi * xi_gradient
        center_r_gradient = curve.dr_dxi * xi_gradient
        center_x_curvature = (
            curve.d2x_dxi2 * xi_gradient**2
            + curve.dx_dxi * xi_curvature
        )
        center_r_curvature = (
            curve.d2r_dxi2 * xi_gradient**2
            + curve.dr_dxi * xi_curvature
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

    def validate_operating_interval(self) -> tuple[PivotedRollerContactSample, ...]:
        """Check contact existence, uniqueness, regularity, and non-interference."""

        positions = np.linspace(
            self._spec.axial_position_min,
            self._spec.axial_position_max,
            self._spec.validation_positions,
        )
        samples: list[PivotedRollerContactSample] = []
        for position in positions:
            sample = self.evaluate(float(position))
            self._validate_noninterference(
                axial_position=float(position),
                sample=sample,
            )
            samples.append(sample)
        return tuple(samples)

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
            roots.append(
                float(
                    brentq(
                        lambda xi: self._contact_residual(xi, axial_position),
                        float(xi_values[index]),
                        float(xi_values[index + 1]),
                        xtol=min(1.0e-13, self._spec.coordinate_tolerance / 10.0),
                        rtol=1.0e-13,
                    )
                )
            )

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
        norm = sqrt(1.0 + slope * slope)
        sign = float(self._spec.roller_side_sign)

        normal_x = -sign * slope / norm
        normal_r = sign / norm
        normal_x_gradient = -sign * second / norm**3
        normal_r_gradient = -sign * slope * second / norm**3
        normal_x_curvature = -sign * (
            third / norm**3 - 3.0 * slope * second**2 / norm**5
        )
        normal_r_curvature = -sign * (
            (second**2 + slope * third) / norm**3
            - 3.0 * slope**2 * second**2 / norm**5
        )

        roller = self._spec.roller_radius
        signed_curvature = sign * second / norm**3
        regular_factor = 1.0 - roller * signed_curvature
        if abs(regular_factor) <= 64.0 * np.finfo(float).eps:
            raise ValueError("The roller-center offset curve is singular.")

        return _OffsetCurve(
            x=(
                self._spec.ramp_reference_axial_position
                + axial_position
                + xi
                + roller * normal_x
            ),
            radius=(
                self._spec.ramp_reference_radius
                + profile.value
                + roller * normal_r
            ),
            dx_dxi=1.0 + roller * normal_x_gradient,
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
        profile = self._spec.ramp_profile
        grid = np.linspace(profile.x_min, profile.x_max, self._spec.root_scan_points)
        center_x = sample.roller_center_axial_position
        center_r = sample.roller_center_radius
        roller_squared = self._spec.roller_radius**2

        def clearance_squared(xi: float) -> float:
            ramp = profile.evaluate(float(xi))
            dx = center_x - (
                self._spec.ramp_reference_axial_position + axial_position + xi
            )
            dr = center_r - (self._spec.ramp_reference_radius + ramp.value)
            return dx * dx + dr * dr - roller_squared

        values = np.asarray([clearance_squared(float(xi)) for xi in grid])
        minima: list[tuple[float, float]] = [
            (sample.contact_coordinate, clearance_squared(sample.contact_coordinate))
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
                    "The roller penetrates another portion of the ramp at "
                    f"local axial position {axial_position:.12g}."
                )
            if (
                abs(clearance) <= clearance_tolerance
                and abs(coordinate - sample.contact_coordinate)
                > 8.0 * self._spec.coordinate_tolerance
            ):
                raise ValueError(
                    "The roller has a second physical ramp contact at local "
                    f"axial position {axial_position:.12g}."
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
    """Runtime ``q, J, I`` map compiled from the exact appendix geometry.

    Contact roots and implicit derivatives are solved during construction. A
    clamped cubic spline then provides a cheap, C2 runtime angle map. Shaft
    inertia and its derivative are evaluated from the physical mass moments,
    not independently fitted.
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
        self._geometry.validate_operating_interval()

        positions = np.linspace(
            geometry_spec.axial_position_min,
            geometry_spec.axial_position_max,
            compilation_points,
        )
        exact = tuple(self._geometry.evaluate(float(position)) for position in positions)
        angles = np.unwrap(np.asarray([item.angle for item in exact], dtype=float))
        self._angle_spline = CubicSpline(
            positions,
            angles,
            bc_type=((1, exact[0].angle_gradient), (1, exact[-1].angle_gradient)),
        )

        validation_positions = np.linspace(
            geometry_spec.axial_position_min,
            geometry_spec.axial_position_max,
            2 * compilation_points - 1,
        )
        gradients = np.asarray(self._angle_spline(validation_positions, 1), dtype=float)
        if not np.all(np.isfinite(gradients)) or np.min(gradients) <= 0.0:
            raise ValueError(
                "The compiled fixed-pivot flyweight map reverses or reaches a "
                "singular motion ratio."
            )

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
        """Evaluate the unsplined contact solution for validation and studies."""

        contact = self._geometry.evaluate(axial_position)
        return self._compose_sample(
            angle=contact.angle,
            angle_gradient=contact.angle_gradient,
            angle_curvature=contact.angle_curvature,
        )

    def contact_at(self, axial_position: float) -> PivotedRollerContactSample:
        """Return the exact mechanism contact for geometry diagnostics."""

        return self._geometry.evaluate(axial_position)

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
