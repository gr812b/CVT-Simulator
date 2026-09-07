"""Small JSON-safe expression language for derived CINDER result fields.

The expression layer is deliberately generic.  It knows coordinates, named
report signals, literals, and ordinary mathematical operations; it knows
nothing about CVTs or belt tension.  The same expression document can be
interpreted in Python or by another consumer such as a web frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

import numpy as np

_UNARY_OPS = {"neg", "abs", "exp", "expm1", "sin", "cos", "sqrt"}
_BINARY_OPS = {"add", "sub", "mul", "div", "lt"}
_TERNARY_OPS = {"where"}


@dataclass(frozen=True, slots=True)
class FieldExpression:
    """One node in CINDER's portable derived-field expression tree."""

    op: str
    args: tuple["FieldExpression", ...] = ()
    value: float | None = None
    key: str | None = None

    def __post_init__(self) -> None:
        if self.op == "literal":
            if self.args or self.key is not None or self.value is None:
                raise ValueError("literal expressions require only value.")
            if not isfinite(float(self.value)):
                raise ValueError("literal expression values must be finite.")
            return
        if self.op == "coordinate":
            if self.args or self.key is not None or self.value is not None:
                raise ValueError("coordinate expressions accept no payload.")
            return
        if self.op == "signal":
            if self.args or self.value is not None or not self.key:
                raise ValueError("signal expressions require only a non-empty key.")
            return
        expected = (
            1
            if self.op in _UNARY_OPS
            else 2 if self.op in _BINARY_OPS else 3 if self.op in _TERNARY_OPS else None
        )
        if expected is None:
            raise ValueError(f"Unsupported field-expression operator: {self.op!r}.")
        if len(self.args) != expected or self.value is not None or self.key is not None:
            raise ValueError(
                f"{self.op} expressions require exactly {expected} arguments."
            )

    @classmethod
    def literal(cls, value: float) -> "FieldExpression":
        return cls(op="literal", value=float(value))

    @classmethod
    def coordinate(cls) -> "FieldExpression":
        return cls(op="coordinate")

    @classmethod
    def signal(cls, key: str) -> "FieldExpression":
        return cls(op="signal", key=key)

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-safe public representation of this expression."""

        if self.op == "literal":
            return {"op": "literal", "value": float(self.value)}
        if self.op == "coordinate":
            return {"op": "coordinate"}
        if self.op == "signal":
            return {"op": "signal", "key": self.key}
        return {"op": self.op, "args": [arg.as_dict() for arg in self.args]}

    def evaluate(self, *, coordinate, signals: Mapping[str, Any]):
        """Evaluate this expression for scalar or NumPy-array coordinates."""

        if self.op == "literal":
            return float(self.value)
        if self.op == "coordinate":
            return coordinate
        if self.op == "signal":
            try:
                return signals[self.key]  # type: ignore[index]
            except KeyError as error:
                raise KeyError(
                    "Missing report signal required by field expression: "
                    f"{self.key!r}."
                ) from error

        if self.op in _UNARY_OPS:
            value = self.args[0].evaluate(coordinate=coordinate, signals=signals)
            if self.op == "neg":
                return -value
            if self.op == "abs":
                return np.abs(value)
            if self.op == "exp":
                return np.exp(value)
            if self.op == "expm1":
                return np.expm1(value)
            if self.op == "sin":
                return np.sin(value)
            if self.op == "cos":
                return np.cos(value)
            if self.op == "sqrt":
                return np.sqrt(value)

        if self.op == "where":
            condition = self.args[0].evaluate(coordinate=coordinate, signals=signals)
            true_value = self.args[1].evaluate(coordinate=coordinate, signals=signals)
            with np.errstate(all="ignore"):
                false_value = self.args[2].evaluate(
                    coordinate=coordinate, signals=signals
                )
            return np.where(condition, true_value, false_value)

        left = self.args[0].evaluate(coordinate=coordinate, signals=signals)
        right = self.args[1].evaluate(coordinate=coordinate, signals=signals)
        with np.errstate(all="ignore"):
            if self.op == "add":
                return left + right
            if self.op == "sub":
                return left - right
            if self.op == "mul":
                return left * right
            if self.op == "div":
                return left / right
            if self.op == "lt":
                return left < right
        raise RuntimeError(f"Unhandled field-expression operator: {self.op!r}.")

    def __add__(self, other) -> "FieldExpression":
        return binary("add", self, other)

    def __radd__(self, other) -> "FieldExpression":
        return binary("add", other, self)

    def __sub__(self, other) -> "FieldExpression":
        return binary("sub", self, other)

    def __rsub__(self, other) -> "FieldExpression":
        return binary("sub", other, self)

    def __mul__(self, other) -> "FieldExpression":
        return binary("mul", self, other)

    def __rmul__(self, other) -> "FieldExpression":
        return binary("mul", other, self)

    def __truediv__(self, other) -> "FieldExpression":
        return binary("div", self, other)

    def __rtruediv__(self, other) -> "FieldExpression":
        return binary("div", other, self)

    def __neg__(self) -> "FieldExpression":
        return unary("neg", self)


def expression(value: FieldExpression | float | int) -> FieldExpression:
    if isinstance(value, FieldExpression):
        return value
    return FieldExpression.literal(float(value))


def unary(op: str, value) -> FieldExpression:
    return FieldExpression(op=op, args=(expression(value),))


def binary(op: str, left, right) -> FieldExpression:
    return FieldExpression(op=op, args=(expression(left), expression(right)))


def where(condition, true_value, false_value) -> FieldExpression:
    return FieldExpression(
        op="where",
        args=(expression(condition), expression(true_value), expression(false_value)),
    )


def abs_expr(value) -> FieldExpression:
    return unary("abs", value)


def expm1_expr(value) -> FieldExpression:
    return unary("expm1", value)


def sin_expr(value) -> FieldExpression:
    return unary("sin", value)


def cos_expr(value) -> FieldExpression:
    return unary("cos", value)


def sqrt_expr(value) -> FieldExpression:
    return unary("sqrt", value)


def less_than(left, right) -> FieldExpression:
    return binary("lt", left, right)
