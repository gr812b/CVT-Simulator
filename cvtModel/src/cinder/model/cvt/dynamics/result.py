"""Immutable diagnostics returned by one generic trial closure solve."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.closure import (
    CLOSURE_UNKNOWN_COUNT,
    ClosureEquation,
    ClosureUnknowns,
)

if TYPE_CHECKING:
    from .trial_system import TrialClosureSystem


@dataclass(frozen=True, slots=True)
class ClosureEquationResidual:
    """Residual of one named zero-equals closure equation after a solve."""

    name: str
    value: float

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("ClosureEquationResidual.name must be non-empty.")
        if not isfinite(self.value):
            raise ValueError("ClosureEquationResidual.value must be finite.")


@dataclass(frozen=True, slots=True)
class TrialClosureRuntimeResult:
    """Lean closure outcome retained by the numerical runtime path.

    The RHS needs only solved closure unknowns.  Matrix condition numbers,
    rank, named residuals, and immutable matrix copies are audit diagnostics
    and are materialized separately by :meth:`TrialClosureSystem.solve`.
    """

    unknowns: ClosureUnknowns

    def __post_init__(self) -> None:
        if not isinstance(self.unknowns, ClosureUnknowns):
            raise TypeError("unknowns must be a ClosureUnknowns instance.")


@dataclass(frozen=True, slots=True)
class TrialClosureResult:
    """Full auditable outcome of one affine closure solve.

    This result intentionally contains no CVT-specific contact logic. It is
    useful both while building individual rows and later inside trial-lambda
    evaluations. ``equation_residuals`` remain in the same order as
    ``equations`` and the matrix rows.
    """

    system: "TrialClosureSystem"
    equations: tuple[ClosureEquation, ...]
    matrix: NDArray[np.float64]
    right_hand_side: NDArray[np.float64]
    unknowns: ClosureUnknowns
    equation_residuals: tuple[ClosureEquationResidual, ...]
    condition_number: float
    matrix_rank: int
    scaled_condition_number: float | None = None

    def __post_init__(self) -> None:
        equation_count = len(self.equations)
        if equation_count != CLOSURE_UNKNOWN_COUNT:
            raise ValueError(
                "equations must contain exactly "
                f"{CLOSURE_UNKNOWN_COUNT} closure rows."
            )
        if equation_count != len(self.equation_residuals):
            raise ValueError(
                "equations and equation_residuals must have the same length."
            )

        equation_names = tuple(equation.name for equation in self.equations)
        residual_names = tuple(residual.name for residual in self.equation_residuals)
        if equation_names != residual_names:
            raise ValueError(
                "equation_residuals must match equations in the same order."
            )

        _validate_matrix(
            self.matrix,
            name="matrix",
            expected_shape=(CLOSURE_UNKNOWN_COUNT, CLOSURE_UNKNOWN_COUNT),
        )
        _validate_vector(
            self.right_hand_side,
            name="right_hand_side",
            expected_length=CLOSURE_UNKNOWN_COUNT,
        )

        if not isfinite(self.condition_number) and self.condition_number != float(
            "inf"
        ):
            raise ValueError("condition_number must be finite or positive infinity.")
        if self.condition_number < 0.0:
            raise ValueError("condition_number must be non-negative.")
        if self.scaled_condition_number is not None:
            if not isfinite(
                self.scaled_condition_number
            ) and self.scaled_condition_number != float("inf"):
                raise ValueError(
                    "scaled_condition_number must be finite or positive infinity."
                )
            if self.scaled_condition_number < 0.0:
                raise ValueError("scaled_condition_number must be non-negative.")
        if not 0 <= self.matrix_rank <= CLOSURE_UNKNOWN_COUNT:
            raise ValueError(
                "matrix_rank must lie between 0 and " f"{CLOSURE_UNKNOWN_COUNT}."
            )

        object.__setattr__(self, "matrix", _immutable_float_array(self.matrix))
        object.__setattr__(
            self,
            "right_hand_side",
            _immutable_float_array(self.right_hand_side),
        )

    @property
    def solution_vector(self) -> NDArray[np.float64]:
        """Return the solved unknowns in canonical closure column order."""

        return _immutable_float_array(np.asarray(self.unknowns.as_tuple(), dtype=float))

    @property
    def max_abs_equation_residual(self) -> float:
        """Largest absolute residual among the imposed closure equations."""

        return max(abs(residual.value) for residual in self.equation_residuals)

    def residual_for(self, equation_name: str) -> float:
        """Return the residual of one named equation."""

        for residual in self.equation_residuals:
            if residual.name == equation_name:
                return residual.value
        raise KeyError(f"No closure equation named {equation_name!r}.")


def _immutable_float_array(
    values: NDArray[np.float64] | np.ndarray,
) -> NDArray[np.float64]:
    array = np.array(values, dtype=float, copy=True)
    array.setflags(write=False)
    return array


def _validate_matrix(
    values: NDArray[np.float64] | np.ndarray,
    *,
    name: str,
    expected_shape: tuple[int, int],
) -> None:
    array = np.asarray(values, dtype=float)
    if array.shape != expected_shape:
        raise ValueError(f"{name} must have shape {expected_shape}, got {array.shape}.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")


def _validate_vector(
    values: NDArray[np.float64] | np.ndarray,
    *,
    name: str,
    expected_length: int,
) -> None:
    array = np.asarray(values, dtype=float)
    if array.shape != (expected_length,):
        raise ValueError(
            f"{name} must have shape ({expected_length},), got {array.shape}."
        )
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")
