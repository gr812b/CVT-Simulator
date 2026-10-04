"""Keep legacy tuning hints aligned with the assembly they actually describe."""

from copy import deepcopy
from typing import Any


def readable_tuning_schema(assembly: dict, schema: dict) -> dict:
    """Resolve mount renames and omit controls absent from this hardware version.

    In particular, a fixed-pivot flyweight has mass moments instead of the old
    point-mass parameter. Do not invent a conversion or expose an ineffective
    input. Its full physical editing surface belongs to the design editor.
    """
    result = deepcopy(schema)
    parameters = []
    for original in schema.get("parameters", []):
        parameter = deepcopy(original)
        path = parameter.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        parts = [
            part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]
        ]
        if len(parts) > 1 and parts[0] == "pulleys":
            current_mount = {"input": "primary", "output": "secondary"}.get(parts[1])
            pulleys = assembly.get("pulleys", {})
            if parts[1] not in pulleys and current_mount in pulleys:
                parts[1] = current_mount
        value: Any = assembly
        try:
            for part in parts:
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        parameter["path"] = "/" + "/".join(
            part.replace("~", "~0").replace("/", "~1") for part in parts
        )
        parameter["default"] = deepcopy(value)
        parameters.append(parameter)
    result["parameters"] = parameters
    return result
