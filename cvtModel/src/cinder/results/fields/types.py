"""Generic domains, fields, and materialized samples for CINDER results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Mapping

import numpy as np
from numpy.typing import NDArray

from .expression import FieldExpression

if TYPE_CHECKING:
    from cinder.results.reporting import CVTIntegrationResult


@dataclass(frozen=True, slots=True)
class SpatialRegionDefinition:
    """One parameterized region of a spatial result domain."""

    key: str
    label: str
    length: FieldExpression
    x: FieldExpression
    y: FieldExpression

    def __post_init__(self) -> None:
        if not self.key or not self.label:
            raise ValueError("Spatial region key and label must be non-empty.")


@dataclass(frozen=True, slots=True)
class SpatialDomainDefinition:
    """One reusable spatial domain shared by one or more result fields."""

    key: str
    label: str
    description: str
    regions: tuple[SpatialRegionDefinition, ...]
    periodic: bool = False
    embedding_unit: str = "m"

    def __post_init__(self) -> None:
        if not self.key or not self.label or not self.embedding_unit:
            raise ValueError("Spatial domain metadata must be non-empty.")
        if not self.regions:
            raise ValueError("SpatialDomainDefinition requires at least one region.")
        keys = [region.key for region in self.regions]
        if len(keys) != len(set(keys)):
            raise ValueError("Spatial domain region keys must be unique.")


@dataclass(frozen=True, slots=True)
class SpatialFieldDefinition:
    """One scalar field expressed over a named spatial domain."""

    key: str
    label: str
    unit: str
    group: str
    domain_key: str
    description: str
    regions: Mapping[str, FieldExpression]

    def __post_init__(self) -> None:
        if not self.key or not self.label or not self.unit or not self.group or not self.domain_key:
            raise ValueError("Spatial field metadata must be non-empty.")
        if not self.regions:
            raise ValueError("SpatialFieldDefinition requires at least one region expression.")
        object.__setattr__(self, "regions", dict(self.regions))


@dataclass(frozen=True, slots=True)
class SpatialDomainSample:
    """One materialized spatial domain at one report frame."""

    coordinate: NDArray[np.float64]
    local_coordinate: NDArray[np.float64]
    region_keys: tuple[str, ...]
    position: NDArray[np.float64]

    def __post_init__(self) -> None:
        coordinate = _freeze_vector(self.coordinate, "coordinate")
        local = _freeze_vector(self.local_coordinate, "local_coordinate")
        position = np.asarray(self.position, dtype=float)
        if position.ndim != 2 or position.shape != (coordinate.size, 2):
            raise ValueError("position must have shape (sample_count, 2).")
        if not np.all(np.isfinite(position)):
            raise ValueError("position values must be finite.")
        frozen_position = np.array(position, dtype=float, copy=True)
        frozen_position.setflags(write=False)
        if local.size != coordinate.size or len(self.region_keys) != coordinate.size:
            raise ValueError("Spatial sample arrays must have matching lengths.")
        object.__setattr__(self, "coordinate", coordinate)
        object.__setattr__(self, "local_coordinate", local)
        object.__setattr__(self, "position", frozen_position)


@dataclass(frozen=True, slots=True)
class SpatialFieldSample:
    """One scalar spatial field materialized at one report frame."""

    field_key: str
    unit: str
    domain: SpatialDomainSample
    values: NDArray[np.float64]

    def __post_init__(self) -> None:
        values = np.asarray(self.values, dtype=float)
        if values.ndim != 1 or values.size != self.domain.coordinate.size:
            raise ValueError("field sample values must align with the domain sample.")
        if not np.all(np.isfinite(values) | np.isnan(values)):
            raise ValueError("field sample values must be finite or NaN.")
        frozen = np.array(values, dtype=float, copy=True)
        frozen.setflags(write=False)
        object.__setattr__(self, "values", frozen)


@dataclass(frozen=True, slots=True)
class SpatialFieldSeries:
    """One field fully materialized over the flattened report-time table."""

    field_key: str
    unit: str
    time: NDArray[np.float64]
    coordinate: NDArray[np.float64]
    position: NDArray[np.float64]
    values: NDArray[np.float64]

    def __post_init__(self) -> None:
        time = _freeze_vector(self.time, "time")
        coordinate = _freeze_vector(self.coordinate, "coordinate")
        position = np.asarray(self.position, dtype=float)
        values = np.asarray(self.values, dtype=float)
        expected = (time.size, coordinate.size)
        if position.shape != (time.size, coordinate.size, 2):
            raise ValueError("position must have shape (time, coordinate, 2).")
        if values.shape != expected:
            raise ValueError("values must have shape (time, coordinate).")
        if not np.all(np.isfinite(position)):
            raise ValueError("position values must be finite.")
        if not np.all(np.isfinite(values) | np.isnan(values)):
            raise ValueError("field values must be finite or NaN.")
        frozen_position = np.array(position, dtype=float, copy=True)
        frozen_values = np.array(values, dtype=float, copy=True)
        frozen_position.setflags(write=False)
        frozen_values.setflags(write=False)
        object.__setattr__(self, "time", time)
        object.__setattr__(self, "coordinate", coordinate)
        object.__setattr__(self, "position", frozen_position)
        object.__setattr__(self, "values", frozen_values)


class BoundSpatialDomain:
    """A spatial-domain definition bound to one materialized CINDER result."""

    def __init__(self, result: "CVTIntegrationResult", definition: SpatialDomainDefinition) -> None:
        self.result = result
        self.definition = definition

    def sample(self, frame_index: int, *, count: int = 200) -> SpatialDomainSample:
        if count < 4:
            raise ValueError("count must be at least 4.")
        signals = _frame_signals(self.result, frame_index)
        lengths = np.asarray(
            [
                float(region.length.evaluate(coordinate=0.0, signals=signals))
                for region in self.definition.regions
            ],
            dtype=float,
        )
        if not np.all(np.isfinite(lengths)) or np.any(lengths <= 0.0):
            raise ValueError("Spatial domain region lengths must be positive and finite.")
        cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
        total_length = float(cumulative[-1])
        distances = np.linspace(
            0.0,
            total_length,
            num=count,
            endpoint=not self.definition.periodic,
            dtype=float,
        )
        region_indices = np.searchsorted(cumulative[1:], distances, side="right")
        region_indices = np.minimum(region_indices, len(self.definition.regions) - 1)
        local = (distances - cumulative[region_indices]) / lengths[region_indices]
        local = np.clip(local, 0.0, 1.0)
        position = np.empty((count, 2), dtype=float)
        region_keys = [""] * count
        for region_index, region in enumerate(self.definition.regions):
            mask = region_indices == region_index
            if not np.any(mask):
                continue
            u = local[mask]
            position[mask, 0] = region.x.evaluate(coordinate=u, signals=signals)
            position[mask, 1] = region.y.evaluate(coordinate=u, signals=signals)
            for index in np.flatnonzero(mask):
                region_keys[int(index)] = region.key
        coordinate = distances / total_length
        return SpatialDomainSample(
            coordinate=coordinate,
            local_coordinate=local,
            region_keys=tuple(region_keys),
            position=position,
        )


class BoundSpatialField:
    """A field definition bound to one result with lazy sample/materialize APIs."""

    def __init__(self, result: "CVTIntegrationResult", definition: SpatialFieldDefinition) -> None:
        self.result = result
        self.definition = definition

    @property
    def key(self) -> str:
        return self.definition.key

    @property
    def unit(self) -> str:
        return self.definition.unit

    @property
    def domain(self) -> BoundSpatialDomain:
        return self.result.domain(self.definition.domain_key)

    def sample(self, frame_index: int, *, count: int = 200) -> SpatialFieldSample:
        domain = self.domain.sample(frame_index, count=count)
        signals = _frame_signals(self.result, frame_index)
        values = np.full(count, np.nan, dtype=float)
        for region_key, expr in self.definition.regions.items():
            mask = np.asarray([key == region_key for key in domain.region_keys], dtype=bool)
            if np.any(mask):
                values[mask] = expr.evaluate(
                    coordinate=domain.local_coordinate[mask], signals=signals
                )
        return SpatialFieldSample(
            field_key=self.definition.key,
            unit=self.definition.unit,
            domain=domain,
            values=values,
        )

    def materialize(self, *, count: int = 200) -> SpatialFieldSeries:
        time = _flatten_time(self.result)
        if time.size == 0:
            raise ValueError("Cannot materialize a field from an empty result.")
        first = self.sample(0, count=count)
        coordinate = first.domain.coordinate
        positions = np.empty((time.size, count, 2), dtype=float)
        values = np.empty((time.size, count), dtype=float)
        positions[0] = first.domain.position
        values[0] = first.values
        for frame_index in range(1, time.size):
            sample = self.sample(frame_index, count=count)
            positions[frame_index] = sample.domain.position
            values[frame_index] = sample.values
        return SpatialFieldSeries(
            field_key=self.definition.key,
            unit=self.definition.unit,
            time=time,
            coordinate=coordinate,
            position=positions,
            values=values,
        )


def _flatten_time(result: "CVTIntegrationResult") -> NDArray[np.float64]:
    if not result.segments:
        return np.empty(0, dtype=float)
    values = np.concatenate([np.asarray(segment.time, dtype=float) for segment in result.segments])
    values.setflags(write=False)
    return values


def _frame_signals(result: "CVTIntegrationResult", frame_index: int) -> dict[str, float]:
    if not isinstance(frame_index, int):
        raise TypeError("frame_index must be an integer.")
    total = sum(segment.time.size for segment in result.segments)
    if frame_index < 0:
        frame_index += total
    if frame_index < 0 or frame_index >= total:
        raise IndexError(f"frame_index {frame_index} is outside [0, {total}).")
    offset = frame_index
    for segment in result.segments:
        if offset < segment.time.size:
            return {
                key: float(signal.values[offset])
                for key, signal in segment.signals.items()
            }
        offset -= segment.time.size
    raise RuntimeError("Failed to resolve report frame index.")


def _freeze_vector(values, name: str) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite vector.")
    frozen = np.array(array, dtype=float, copy=True)
    frozen.setflags(write=False)
    return frozen
