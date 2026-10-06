"""Bounded memoization of pure CINDER preflight reports, never run results."""

import copy
import json
from functools import lru_cache

from app.application.cinder_gateway import CinderGateway


@lru_cache(maxsize=64)
def _report(kind: str, serialized: str):
    gateway = CinderGateway()
    validator = (
        gateway.validate_assembly if kind == "assembly" else gateway.validate_simulation_case
    )
    return validator(json.loads(serialized))


def validate_assembly(document):
    return copy.deepcopy(_report("assembly", json.dumps(document, sort_keys=True, allow_nan=False)))


def validate_case(document):
    return copy.deepcopy(_report("case", json.dumps(document, sort_keys=True, allow_nan=False)))
