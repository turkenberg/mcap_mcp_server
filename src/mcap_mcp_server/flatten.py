"""Flatten nested dicts into dot-notation column names for DataFrame construction."""

from __future__ import annotations

import json
from typing import Any


def flatten_dict(
    d: dict[str, Any],
    max_depth: int = 3,
    separator: str = "_",
    _prefix: str = "",
    _current_depth: int = 0,
) -> dict[str, Any]:
    """Recursively flatten a nested dict.

    Keys are joined with *separator*. Beyond *max_depth*, remaining nested
    structures are serialised as JSON strings.

    Examples
    --------
    >>> flatten_dict({"pose": {"position": {"x": 1.0}}})
    {'pose_position_x': 1.0}
    """
    items: dict[str, Any] = {}
    for key, value in d.items():
        new_key = f"{_prefix}{separator}{key}" if _prefix else key
        if isinstance(value, dict):
            if _current_depth < max_depth - 1:
                items.update(
                    flatten_dict(
                        value,
                        max_depth=max_depth,
                        separator=separator,
                        _prefix=new_key,
                        _current_depth=_current_depth + 1,
                    )
                )
            else:
                items[new_key] = json.dumps(value)
        elif isinstance(value, (list, tuple)):
            items[new_key] = json.dumps(value)
        else:
            items[new_key] = value
    return items
