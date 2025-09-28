# backend/models/auto_model.py
from dataclasses import is_dataclass, fields as dc_fields
from typing import Any, get_origin, get_args, Union, Type
from pydantic import BaseModel, ConfigDict, create_model

_cache: dict[type, type[BaseModel]] = {}

def model_from_dataclass(dc_type: type) -> type[BaseModel]:
    if dc_type in _cache:
        return _cache[dc_type]
    if not is_dataclass(dc_type):
        raise TypeError(f"{dc_type} is not a dataclass")

    annotations: dict[str, tuple[type[Any], Any]] = {}
    for f in dc_fields(dc_type):
        t = f.type
        origin = get_origin(t)
        if origin is Union:
            args = []
            for a in get_args(t):
                args.append(model_from_dataclass(a) if is_dataclass(a) else a)
            field_type = Union[tuple(args)]  # type: ignore[arg-type]
        else:
            field_type = model_from_dataclass(t) if is_dataclass(t) else t
        annotations[f.name] = (field_type, ...)  # required

    M = create_model(f"{dc_type.__name__}Model", __base__=BaseModel, **annotations)  # type: ignore
    # attach config
    M.model_config = ConfigDict(from_attributes=True)
    _cache[dc_type] = M
    return M
