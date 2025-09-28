# backend/models/auto_model.py
from __future__ import annotations
import inspect
from dataclasses import is_dataclass, fields as dc_fields
from typing import Any, Dict, Tuple, Union, get_args, get_origin, get_type_hints
from pydantic import BaseModel, ConfigDict, create_model

_CACHE: dict[type, type[BaseModel]] = {}
_PRIMS = (int, float, str, bool, bytes, type(None))

def _resolve(t: Any) -> Any:
    origin = get_origin(t)
    if origin is Union:
        return Union[tuple(_resolve(a) for a in get_args(t))]  # type: ignore[misc]
    if origin in (list, tuple, set, frozenset):
        (inner,) = get_args(t) or (Any,)
        return origin[_resolve(inner)]  # type: ignore[index]
    if origin is dict:
        k_t, v_t = get_args(t) or (Any, Any)
        return dict[_resolve(k_t), _resolve(v_t)]  # type: ignore[index]
    if inspect.isclass(t) and t not in _PRIMS:
        return model_from_class(t)
    return t

def model_from_class(tp: type, *, name: str | None = None) -> type[BaseModel]:
    if tp in _CACHE:
        return _CACHE[tp]
    if not inspect.isclass(tp):
        raise TypeError(f"{tp!r} is not a class")

    # 1) Prefer class annotations (DRY). Only if there are NONE do we fall back to __init__.
    fields_dict: Dict[str, Tuple[Any, Any]] = {}
    hints: Dict[str, Any] = {}
    try:
        hints = get_type_hints(tp, include_extras=True) or {}
    except Exception:
        hints = getattr(tp, "__annotations__", {}) or {}

    if hints:
        for name_, ann in hints.items():
            fields_dict[name_] = (_resolve(ann), ...)
    else:
        # 2) Fallback: derive fields from __init__ signature
        try:
            sig = inspect.signature(tp.__init__)
            for name_, p in sig.parameters.items():
                if name_ == "self":
                    continue
                ann = p.annotation if p.annotation is not inspect._empty else Any
                fields_dict[name_] = (_resolve(ann), ...)
        except Exception:
            pass

    model_name = name or f"{tp.__name__}Model"
    M = create_model(model_name, __base__=BaseModel, **fields_dict)  # type: ignore[arg-type]
    M.model_config = ConfigDict(from_attributes=True, title=model_name)
    _CACHE[tp] = M
    return M
