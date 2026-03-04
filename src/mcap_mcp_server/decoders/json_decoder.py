"""Built-in JSON message decoder — no optional dependencies required."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcap_mcp_server.decoders.base import JSON_SCHEMA_TYPE_MAP, FieldInfo
from mcap_mcp_server.flatten import flatten_dict

logger = logging.getLogger(__name__)

_SUPPORTED_ENCODINGS = frozenset({"json"})
_SUPPORTED_SCHEMA_ENCODINGS = frozenset({"jsonschema", "json", ""})


class JsonDecoder:
    """Decode JSON-encoded MCAP messages and extract field info from JSON Schema."""

    def __init__(self, flatten_depth: int = 3) -> None:
        self._flatten_depth = flatten_depth

    def can_decode(self, message_encoding: str, schema_encoding: str) -> bool:
        return (
            message_encoding.lower() in _SUPPORTED_ENCODINGS
            and schema_encoding.lower() in _SUPPORTED_SCHEMA_ENCODINGS
        )

    def decode(self, schema: bytes, data: bytes, **kwargs: Any) -> dict[str, Any]:
        """Decode a JSON message and flatten nested structures."""
        raw = json.loads(data)
        if isinstance(raw, dict):
            return flatten_dict(raw, max_depth=self._flatten_depth)
        return {"value": raw}

    def get_field_info(self, schema: bytes, schema_encoding: str) -> list[FieldInfo]:
        """Extract field names and types from a JSON Schema definition."""
        if not schema:
            return []
        try:
            schema_obj = json.loads(schema)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Failed to parse JSON schema, returning empty field info")
            return []
        return _extract_fields_from_json_schema(schema_obj, self._flatten_depth)


def _extract_fields_from_json_schema(
    schema: dict,
    max_depth: int,
    prefix: str = "",
    depth: int = 0,
    separator: str = "_",
) -> list[FieldInfo]:
    """Walk a JSON Schema ``properties`` tree and emit flattened FieldInfo entries."""
    fields: list[FieldInfo] = []
    properties = schema.get("properties", {})

    for name, prop in properties.items():
        full_name = f"{prefix}{separator}{name}" if prefix else name
        prop_type = prop.get("type", "string")
        description = prop.get("description", "")

        if prop_type == "object" and depth < max_depth - 1:
            fields.extend(
                _extract_fields_from_json_schema(
                    prop, max_depth, prefix=full_name, depth=depth + 1, separator=separator
                )
            )
        else:
            duckdb_type = JSON_SCHEMA_TYPE_MAP.get(prop_type, "VARCHAR")
            fields.append(FieldInfo(name=full_name, type=duckdb_type, description=description))

    return fields
