"""Generic state- and lambda-agnostic affine closure solve."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

import numpy as np
from numpy.typing import NDArray

from cinder.closure import CLOSURE_UNKNOWN_COUNT, ClosureEquation, ClosureUnknowns

from .result import ClosureEquationResidual, TrialClosureResult


class TrialClosureSolveError(RuntimeError):
    """Raised when a trial closure system cannot be solved robustly."""


class TrialClosureConditionError(TrialClosureSolveError):
    """Raised when an optional matrix-condition threshold is exceeded."""


@dataclass(frozen=True, slots=True)
class TrialClosureSystem:
    """One fully assembled affine closure system.

    This class deliberately knows nothing about CVT geometry, wrap mechanics,
    snapshots, or trial friction utilizations. A CVT-specific builder supplies
    one :class:`~cinder.closure.ClosureEquation` for every canonical closure
    unknown from one frozen dynamics snapshot and one trial
    ``(lambda_p, lambda_s)`` pair.

    Every equation is written in residual form:

        bias + gains.dot(z) = 0.

    This class performs the common conversion to:

        A z = b,

    solves it, and returns named residual diagnostics.
    """

    equations: tuple[ClosureEquation, ...]

    def __post_init__(self) -> None:
        if len(self.equations) != CLOSURE_UNKNOWN_COUNT:
            raise ValueError(
                "TrialClosureSystem requires exactly "
                f"{CLOSURE_UNKNOWN_COUNT} equations, got {len(self.equations)}."
            )

        for equation in self.equations:
            if not isinstance(equation, ClosureEquation):
                raise TypeError(
                    "TrialClosureSystem.equations must contain only "
                    "ClosureEquation objects."
                )

        equation_names = tuple(equation.name for equation in self.equations)
        if len(set(equation_names)) != len(equation_names):
            raise ValueError("TrialClosureSystem equation names must be unique.")

    @classmethod
    def from_equations(
        cls,
        equations: Iterable[ClosureEquation],
    ) -> "TrialClosureSystem":
        """Construct a system from any iterable while freezing row order."""

        return cls(equations=tuple(equations))

    @property
    def equation_names(self) -> tuple[str, ...]:
        """Return row names in matrix order."""

        return tuple(equation.name for equation in self.equations)

    def assemble(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Return a fresh immutable ``(A, b)`` pair for ``A z = b``.

        The caller receives immutable arrays so accidental mutation cannot make
        the named equations and displayed matrix disagree. NumPy's solver reads
        these arrays without modification.
        """

        matrix = np.asarray(
            [equation.matrix_row for equation in self.equations],
            dtype=float,
        )
        right_hand_side = np.asarray(
            [equation.right_hand_side for equation in self.equations],
            dtype=float,
        )

        expected_matrix_shape = (CLOSURE_UNKNOWN_COUNT, CLOSURE_UNKNOWN_COUNT)
        expected_vector_shape = (CLOSURE_UNKNOWN_COUNT,)
        if matrix.shape != expected_matrix_shape:
            raise ValueError(
                "closure matrix must have shape "
                f"{expected_matrix_shape}, got {matrix.shape}."
            )
        if right_hand_side.shape != expected_vector_shape:
            raise ValueError(
                "closure right-hand side must have shape "
                f"{expected_vector_shape}, got {right_hand_side.shape}."
            )

        _require_finite_array(matrix, name="closure matrix")
        _require_finite_array(right_hand_side, name="closure right-hand side")

        matrix.setflags(write=False)
        right_hand_side.setflags(write=False)
        return matrix, right_hand_side

    def solve(
        self,
        *,
        maximum_condition_number: float | None = None,
    ) -> TrialClosureResult:
        """Solve this system and return the full named diagnostic result.

        ``maximum_condition_number`` is optional because early row-by-row work
        benefits from seeing the actual condition number rather than rejecting a
        configuration solely due to a provisional threshold. When supplied, it
        must be a positive finite value and is checked before solving.
        """

        _validate_condition_limit(maximum_condition_number)
        matrix, right_hand_side = self.assemble()

        condition_number = float(np.linalg.cond(matrix))
        matrix_rank = int(np.linalg.matrix_rank(matrix))

        if maximum_condition_number is not None and (
            not isfinite(condition_number)
            or condition_number > maximum_condition_number
        ):
            raise TrialClosureConditionError(
                "Trial closure matrix condition number "
                f"{condition_number:.6g} exceeds configured limit "
                f"{maximum_condition_number:.6g}."
            )

        try:
            solution_vector = np.linalg.solve(matrix, right_hand_side)
        except np.linalg.LinAlgError as error:
            raise TrialClosureSolveError(
                "Trial closure matrix is singular and cannot be solved."
            ) from error

        _require_finite_array(solution_vector, name="closure solution")
        unknowns = ClosureUnknowns.from_ordered_values(solution_vector)
        equation_residuals = tuple(
            ClosureEquationResidual(
                name=equation.name,
                value=equation.evaluate(unknowns),
            )
            for equation in self.equations
        )

        return TrialClosureResult(
            system=self,
            equations=self.equations,
            matrix=matrix,
            right_hand_side=right_hand_side,
            unknowns=unknowns,
            equation_residuals=equation_residuals,
            condition_number=condition_number,
            matrix_rank=matrix_rank,
        )


def _validate_condition_limit(value: float | None) -> None:
    if value is None:
        return
    if not isfinite(value) or value <= 0.0:
        raise ValueError(
            "maximum_condition_number must be finite and strictly positive."
        )


def _require_finite_array(values: NDArray[np.float64], *, name: str) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must contain only finite values.")
