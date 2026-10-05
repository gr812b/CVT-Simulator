"""Offline school catalog drawn from official Baja SAE result tables."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def school_catalog():
    return json.loads(
        (Path(__file__).parents[1] / "data" / "baja_schools.json").read_text(
            encoding="utf-8"
        )
    )


def known_school(value: str) -> str:
    value = value.strip()
    if value and value not in school_catalog()["schools"]:
        raise ValueError("Choose a school from the list, or leave it blank.")
    return value
