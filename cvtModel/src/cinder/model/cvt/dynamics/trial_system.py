"""Generic state- and lambda-agnostic affine closure solve."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.closure import (
    CLOSURE_UNKNOWN_COUNT,
    ClosureEquation,
    ClosureUnknowns,
)

from .result import (
    ClosureEquationResidual,
    TrialClosureResult,
    TrialClosureRuntimeResult,
)


class TrialClosureSolveError(RuntimeError):
    """Raised when a trial closure system cannot be solved robustly."""


class TrialClosureConditionError(TrialClosureSolveError):
    """Raised when an optional matrix-condition threshold is exceeded."""


@dataclass(frozen=True, slots=True)
class TrialClosureSystem:
    """One fully assembled affine closure system.

    This class deliberately knows nothing about CVT geometry, wrap mechanics,
    snapshots, or trial friction utilizations. A CVT-specific builder supplies
    one :class:`~cinder.model.cvt.closure.ClosureEquation` for every canonical closure
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

    def solve_runtime(
        self,
        *,
        maximum_condition_number: float | None = None,
    ) -> TrialClosureRuntimeResult:
        """Solve the closure for the RHS without allocating audit diagnostics.

        The hot path requires only the eight solved unknowns.  A condition
        number is evaluated only when a configured safety threshold requires
        it; rank, residual records, and immutable matrix copies remain in the
        explicit diagnostic :meth:`solve` path.
        """

        _validate_condition_limit(maximum_condition_number)
        matrix, right_hand_side = self.assemble()
        solution_vector, scaled_condition_number = _solve_equilibrated(
            matrix, right_hand_side
        )
        _check_condition_limit(
            scaled_condition_number, maximum_condition_number=maximum_condition_number
        )
        return TrialClosureRuntimeResult(
            unknowns=ClosureUnknowns.from_ordered_values(solution_vector)
        )

    def solve(
        self,
        *,
        maximum_condition_number: float | None = None,
    ) -> TrialClosureResult:
        """Solve this system and materialize full named audit diagnostics."""

        _validate_condition_limit(maximum_condition_number)
        matrix, right_hand_side = self.assemble()
        condition_number = float(np.linalg.cond(matrix))
        matrix_rank = int(np.linalg.matrix_rank(matrix))
        solution_vector, scaled_condition_number = _solve_equilibrated(
            matrix, right_hand_side
        )
        _check_condition_limit(
            scaled_condition_number, maximum_condition_number=maximum_condition_number
        )
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
            scaled_condition_number=scaled_condition_number,
        )


def _solve_equilibrated(
    matrix: NDArray[np.float64],
    right_hand_side: NDArray[np.float64],
) -> tuple[NDArray[np.float64], float]:
    """Solve an algebraically identical row/column-equilibrated system.

    The physical closure remains ``A z = b``. Numerical scaling constructs

        A_s = D_r A D_c,    b_s = D_r b,    z = D_c y,

    solves ``A_s y = b_s``, and maps back to the original physical unknowns.
    Residual auditing therefore still uses the unscaled equations.
    """

    row_norm = np.maximum(np.max(np.abs(matrix), axis=1), np.abs(right_hand_side))
    row_scale = np.where(row_norm > 0.0, 1.0 / row_norm, 1.0)
    row_matrix = row_scale[:, None] * matrix
    row_rhs = row_scale * right_hand_side

    column_norm = np.max(np.abs(row_matrix), axis=0)
    column_scale = np.where(column_norm > 0.0, 1.0 / column_norm, 1.0)
    scaled_matrix = row_matrix * column_scale[None, :]

    scaled_condition_number = float(np.linalg.cond(scaled_matrix))
    try:
        scaled_solution = np.linalg.solve(scaled_matrix, row_rhs)
    except np.linalg.LinAlgError as error:
        raise TrialClosureSolveError(
            "Trial closure matrix is singular and cannot be solved."
        ) from error
    solution = column_scale * scaled_solution
    _require_finite_array(solution, name="closure solution")
    return solution, scaled_condition_number


def _check_condition_limit(
    condition_number: float, *, maximum_condition_number: float | None
) -> None:
    if maximum_condition_number is None:
        return
    if not isfinite(condition_number) or condition_number > maximum_condition_number:
        raise TrialClosureConditionError(
            "Equilibrated trial closure matrix condition number "
            f"{condition_number:.6g} exceeds configured limit "
            f"{maximum_condition_number:.6g}."
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
