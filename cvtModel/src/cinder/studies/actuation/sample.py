"""Sampling of existing pulley actuator clamping-force relations."""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from math import isclose

import numpy as np

from cinder.model.cvt.actuation import (
    HelicalCouplingState,
    PulleyActuationContext,
    PulleyClosureChannels,
)
from cinder.model.cvt.closure import ClosureUnknown, ClosureUnknowns
from cinder.model.system import CVTAssemblySpec, PulleySpec

from .types import (
    ActuationOperatingPoint,
    ActuationResponseCoordinate,
    ActuationStateCoordinate,
    ClampingForceResponseField,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    affine_gain_column_key,
)


def sample_pulley_clamping_force(
    request: PulleyClampingForceStudyRequest,
) -> ClampingForceResponseField:
    """Sample one mounted actuator's real clamping-force relation.

    This is deliberately a thin static wrapper around the production actuator
    path.  It constructs a local context from the selected CVT geometry,
    evaluates ``PulleyActuator.inspect()``, resolves that exact affine relation
    against the requested closure unknowns, and returns numeric columns.  No
    force law is duplicated here.
    """

    _validate_shift_position(request.cvt, request.point.shift_position)
    shape = tuple(len(axis.values) for axis in request.axes)
    axis_grids = np.meshgrid(
        *(np.asarray(axis.values, dtype=float) for axis in request.axes),
        indexing="ij",
    )

    column_values: dict[str, np.ndarray] = {}
    for axis, grid in zip(request.axes, axis_grids, strict=True):
        column_values[axis.column_key] = np.array(grid, dtype=float, copy=True)

    contribution_keys: tuple[str, ...] | None = None
    nonzero_gain_unknowns: set[ClosureUnknown] = set()

    for index in product(*(range(length) for length in shape)):
        point = request.point
        for axis, grid in zip(request.axes, axis_grids, strict=True):
            point = _replace_coordinate(point, axis.coordinate, float(grid[index]))

        actuator, context = _build_pulley_context(
            cvt=request.cvt,
            pulley=request.pulley,
            point=point,
        )
        inspection = actuator.inspect(context)
        current_keys = tuple(item.key for item in inspection.contributions)
        if contribution_keys is None:
            contribution_keys = current_keys
            _allocate_force_columns(column_values, shape, contribution_keys)
        elif current_keys != contribution_keys:
            raise RuntimeError(
                "Actuator contribution keys changed across one response field."
            )

        total = inspection.total_relation
        _store(
            column_values,
            "total_clamping_force_N",
            index,
            total.evaluate(point.closure_unknowns),
        )
        _store(column_values, "total_bias_force_N", index, total.bias)
        for contribution in inspection.contributions:
            _store(
                column_values,
                f"{contribution.key}_clamping_force_N",
                index,
                contribution.relation.evaluate(point.closure_unknowns),
            )
            _store(
                column_values,
                f"{contribution.key}_bias_force_N",
                index,
                contribution.relation.bias,
            )

        for unknown in ClosureUnknown:
            gain = total.gains[unknown]
            if not isclose(gain, 0.0, abs_tol=1.0e-14):
                nonzero_gain_unknowns.add(unknown)
                key = affine_gain_column_key(unknown)
                if key not in column_values:
                    column_values[key] = np.zeros(shape, dtype=float)
                _store(column_values, key, index, gain)

    if contribution_keys is None:  # pragma: no cover - request axes cannot be empty.
        raise RuntimeError("No actuator contribution data was produced.")

    return ClampingForceResponseField(
        pulley=request.pulley,
        axes=request.axes,
        columns=column_values,
    )


def _allocate_force_columns(
    columns: dict[str, np.ndarray],
    shape: tuple[int, ...],
    contribution_keys: tuple[str, ...],
) -> None:
    columns["total_clamping_force_N"] = np.zeros(shape, dtype=float)
    columns["total_bias_force_N"] = np.zeros(shape, dtype=float)
    for key in contribution_keys:
        columns[f"{key}_clamping_force_N"] = np.zeros(shape, dtype=float)
        columns[f"{key}_bias_force_N"] = np.zeros(shape, dtype=float)


def _store(
    columns: dict[str, np.ndarray], key: str, index: tuple[int, ...], value: float
) -> None:
    columns[key][index] = value


def _replace_coordinate(
    point: ActuationOperatingPoint,
    coordinate: ActuationResponseCoordinate,
    value: float,
) -> ActuationOperatingPoint:
    if coordinate is ActuationStateCoordinate.SHIFT_POSITION:
        return replace(point, shift_position=value)
    if coordinate is ActuationStateCoordinate.SHAFT_SPEED:
        return replace(point, shaft_speed=value)
    if coordinate is ActuationStateCoordinate.SHIFT_SPEED:
        return replace(point, shift_speed=value)
    if isinstance(coordinate, ClosureUnknown):
        values = list(point.closure_unknowns.as_tuple())
        values[int(coordinate)] = value
        return replace(
            point, closure_unknowns=ClosureUnknowns.from_ordered_values(values)
        )
    raise TypeError(f"Unsupported actuation response coordinate: {coordinate!r}")


def _build_pulley_context(
    *,
    cvt: CVTAssemblySpec,
    pulley: PulleyLocation,
    point: ActuationOperatingPoint,
) -> tuple[object, PulleyActuationContext]:
    geometry = cvt.geometry.evaluate(point.shift_position)
    pulley_spec: PulleySpec

    if pulley is PulleyLocation.PRIMARY:
        coordinate = geometry.primary_axial_coordinate
        pulley_spec = cvt.pulleys.primary
        closure_channels = PulleyClosureChannels.primary()
        movable_member_rotational_inertia = cvt.inertias.primary.movable_sheave_rotational_inertia
    elif pulley is PulleyLocation.SECONDARY:
        coordinate = geometry.secondary_axial_coordinate
        pulley_spec = cvt.pulleys.secondary
        closure_channels = PulleyClosureChannels.secondary()
        movable_member_rotational_inertia = cvt.inertias.secondary.movable_sheave_rotational_inertia
    else:  # pragma: no cover - PulleyLocation enum exhaustiveness.
        raise TypeError(f"Unsupported pulley location: {pulley!r}")

    coupling_state = None
    if pulley_spec.helical_coupling is not None:
        coupling_state = HelicalCouplingState(
            kinematics=pulley_spec.helical_coupling.evaluate_from_local_coordinate(
                axial_position=coordinate.value,
                d_axial_position_ds=coordinate.d_value_ds,
                d2_axial_position_ds2=coordinate.d2_value_ds2,
            ),
        )

    context = PulleyActuationContext(
        axial_position=coordinate.value,
        axial_speed=coordinate.d_value_ds * point.shift_speed,
        shaft_speed=point.shaft_speed,
        shift_speed=point.shift_speed,
        closure_channels=closure_channels,
        helical_coupling=coupling_state,
        movable_member_rotational_inertia=movable_member_rotational_inertia,
    )
    return pulley_spec.actuator, context


def _validate_shift_position(cvt: CVTAssemblySpec, shift_position: float) -> None:
    maximum = cvt.geometry.spec.max_shift
    if not 0.0 <= shift_position <= maximum:
        raise ValueError(
            "Actuation study shift_position must lie within the CVT geometry range "
            f"[0, {maximum:.12g}] m."
        )
