"""Small helpers for composing subsystem states into one flat ODE vector."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True, slots=True)
class StateBlock:
    """Named contiguous slice in a composed ODE state vector."""

    name: str
    size: int

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("StateBlock.name must be non-empty.")
        if self.size < 1:
            raise ValueError("StateBlock.size must be at least one.")


@dataclass(frozen=True, slots=True)
class StatePatch:
    """Local state replacement emitted by a subsystem transition."""

    block: str
    values: Mapping[int, float]

    def __post_init__(self) -> None:
        if not self.block or not self.block.strip():
            raise ValueError("StatePatch.block must be non-empty.")
        values = {int(key): float(value) for key, value in self.values.items()}
        for index, value in values.items():
            if index < 0:
                raise ValueError("StatePatch indices must be non-negative.")
            if not isfinite(value):
                raise ValueError("StatePatch values must be finite.")
        object.__setattr__(self, "values", values)

    @classmethod
    def empty(cls, block: str = "") -> "StatePatch":
        return cls(block=block or "__empty__", values={})

    @property
    def is_empty(self) -> bool:
        return not self.values


class StateLayout:
    """Named block layout over a flat solver vector."""

    def __init__(self, *blocks: StateBlock) -> None:
        if not blocks:
            raise ValueError("StateLayout requires at least one block.")
        names = [block.name for block in blocks]
        if len(set(names)) != len(names):
            raise ValueError("StateLayout block names must be unique.")
        self._blocks = tuple(blocks)
        offsets: dict[str, slice] = {}
        offset = 0
        for block in self._blocks:
            offsets[block.name] = slice(offset, offset + block.size)
            offset += block.size
        self._slices = offsets
        self._size = offset

    @property
    def size(self) -> int:
        return self._size

    @property
    def blocks(self) -> tuple[StateBlock, ...]:
        return self._blocks

    def view(self, vector: ArrayLike, block: str) -> NDArray[np.float64]:
        values = np.asarray(vector, dtype=float)
        if values.ndim != 1 or values.size != self._size:
            raise ValueError(f"State vector must contain exactly {self._size} entries.")
        result = values[self._slices[block]]
        result.setflags(write=False)
        return result

    def pack(self, **block_values: ArrayLike) -> NDArray[np.float64]:
        vector = np.zeros(self._size, dtype=float)
        for block in self._blocks:
            values = np.asarray(block_values[block.name], dtype=float)
            if values.ndim != 1 or values.size != block.size:
                raise ValueError(
                    f"Block {block.name!r} must contain exactly {block.size} entries."
                )
            vector[self._slices[block.name]] = values
        if not np.all(np.isfinite(vector)):
            raise ValueError("Packed state vector must be finite.")
        vector.setflags(write=False)
        return vector

    def view_matrix(self, matrix, block: str) -> NDArray[np.float64]:
        """Return a named block from a column-major state history matrix."""

        values = np.asarray(matrix, dtype=float)
        if values.ndim != 2 or values.shape[0] != self._size:
            raise ValueError(
                f"State history must have {self._size} rows, one per state entry."
            )
        result = values[self._slices[block], :]
        result.setflags(write=False)
        return result

    def replace_block(
        self, vector: ArrayLike, block: str, values: ArrayLike
    ) -> NDArray[np.float64]:
        """Return ``vector`` with one named block replaced."""

        if block not in self._slices:
            raise KeyError(f"Unknown state block {block!r}.")
        result = np.array(vector, dtype=float, copy=True)
        if result.ndim != 1 or result.size != self._size:
            raise ValueError(f"State vector must contain exactly {self._size} entries.")
        replacement = np.asarray(values, dtype=float)
        block_slice = self._slices[block]
        block_size = block_slice.stop - block_slice.start
        if replacement.ndim != 1 or replacement.size != block_size:
            raise ValueError(
                f"Replacement for block {block!r} must contain {block_size} entries."
            )
        result[block_slice] = replacement
        if not np.all(np.isfinite(result)):
            raise ValueError("Replaced state vector must be finite.")
        result.setflags(write=False)
        return result

    def apply_patches(
        self, vector: ArrayLike, patches: Sequence[StatePatch]
    ) -> NDArray[np.float64]:
        result = np.array(vector, dtype=float, copy=True)
        if result.ndim != 1 or result.size != self._size:
            raise ValueError(f"State vector must contain exactly {self._size} entries.")
        touched: set[tuple[str, int]] = set()
        for patch in patches:
            if patch.is_empty:
                continue
            if patch.block not in self._slices:
                raise KeyError(f"Unknown state block {patch.block!r}.")
            block_slice = self._slices[patch.block]
            block_size = block_slice.stop - block_slice.start
            for local_index, value in patch.values.items():
                if local_index >= block_size:
                    raise IndexError(
                        f"Patch index {local_index} exceeds block {patch.block!r}."
                    )
                key = (patch.block, local_index)
                if key in touched:
                    raise ValueError(
                        f"Multiple patches attempted to update {patch.block}[{local_index}]."
                    )
                touched.add(key)
                result[block_slice.start + local_index] = value
        if not np.all(np.isfinite(result)):
            raise ValueError("Patched state vector must be finite.")
        result.setflags(write=False)
        return result
