"""ROS 2 (CDR) message decoder wrapping mcap-ros2-support."""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any

from mcap_mcp_server.decoders.base import NUMERIC_TYPE_MAP, FieldInfo
from mcap_mcp_server.flatten import flatten_dict

logger = logging.getLogger(__name__)

try:
    from mcap.records import Schema
    from mcap_ros2.decoder import DecoderFactory

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


class Ros2Decoder:
    """Decode ROS 2 CDR-encoded MCAP messages using mcap-ros2-support."""

    def __init__(self, flatten_depth: int = 3) -> None:
        if not _AVAILABLE:
            raise ImportError(
                "mcap-ros2-support is required. "
                "Install with: pip install mcap-mcp-server[ros2]"
            )
        self._flatten_depth = flatten_depth
        self._factory = DecoderFactory()
        self._decoders: dict[int, Any] = {}

    def can_decode(self, message_encoding: str, schema_encoding: str) -> bool:
        return message_encoding == "cdr" and schema_encoding in ("ros2msg", "ros2idl")

    def decode(
        self,
        schema: bytes,
        data: bytes,
        *,
        schema_name: str = "",
        schema_encoding: str = "",
        schema_id: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        decoder_fn = self._get_decoder(schema, schema_name, schema_encoding, schema_id)
        if decoder_fn is None:
            return {}
        msg = decoder_fn(data)
        raw = _namespace_to_dict(msg)
        return flatten_dict(raw, max_depth=self._flatten_depth)

    def get_field_info(self, schema: bytes, schema_encoding: str) -> list[FieldInfo]:
        if schema_encoding not in ("ros2msg", "ros2idl") or not schema:
            return []
        try:
            text = schema.decode("utf-8")
            if schema_encoding == "ros2msg":
                return _parse_ros_msg_def(text, self._flatten_depth)
            return _parse_ros_idl(text, self._flatten_depth)
        except Exception:
            logger.warning("Failed to extract ROS2 field info", exc_info=True)
            return []

    def _get_decoder(
        self, schema_data: bytes, schema_name: str, schema_encoding: str, schema_id: int
    ) -> Any:
        if schema_id in self._decoders:
            return self._decoders[schema_id]

        effective_encoding = "ros2msg" if schema_encoding in ("ros2msg", "ros2idl") else schema_encoding
        schema_rec = Schema(
            id=schema_id, data=schema_data, encoding=effective_encoding, name=schema_name
        )
        decoder_fn = self._factory.decoder_for("cdr", schema_rec)
        if decoder_fn is not None:
            self._decoders[schema_id] = decoder_fn
        return decoder_fn


def _namespace_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a SimpleNamespace (or nested) to a plain dict recursively."""
    if isinstance(obj, SimpleNamespace):
        d = vars(obj)
    elif isinstance(obj, dict):
        d = obj
    elif hasattr(obj, "__dict__"):
        d = obj.__dict__
    else:
        return {"value": obj}

    result: dict[str, Any] = {}
    for key, value in d.items():
        if isinstance(value, (SimpleNamespace, dict)) or (
            hasattr(value, "__dict__") and not isinstance(value, (str, bytes, int, float, bool))
        ):
            result[key] = _namespace_to_dict(value)
        elif isinstance(value, (list, tuple)):
            if value and (isinstance(value[0], SimpleNamespace) or hasattr(value[0], "__dict__")):
                result[key] = [_namespace_to_dict(v) for v in value]
            else:
                result[key] = list(value)
        else:
            result[key] = value
    return result


_FIELD_RE = re.compile(r"^\s*(\w[\w/\[\]]*)\s+(\w+)\s*(?:=.*)?$")


def _parse_ros_msg_def(
    msg_def: str,
    max_depth: int,
    prefix: str = "",
    depth: int = 0,
    separator: str = "_",
) -> list[FieldInfo]:
    """Parse a ROS 2 .msg definition string to extract flattened field info."""
    fields: list[FieldInfo] = []
    for line in msg_def.splitlines():
        line = line.strip()
        if line.startswith("==="):
            break
        if not line or line.startswith("#"):
            continue

        m = _FIELD_RE.match(line)
        if not m:
            continue

        ros_type, name = m.group(1), m.group(2)
        full_name = f"{prefix}{separator}{name}" if prefix else name

        is_array = "[]" in ros_type or "[" in ros_type
        base_type = re.sub(r"\[.*\]", "", ros_type)

        if is_array:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))
        elif base_type in NUMERIC_TYPE_MAP:
            fields.append(FieldInfo(name=full_name, type=NUMERIC_TYPE_MAP[base_type]))
        else:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))

    return fields


_IDL_FIELD_RE = re.compile(r"^\s*(\w[\w:<>,\s]*)\s+(\w+)\s*;")


def _parse_ros_idl(
    idl_text: str,
    max_depth: int,
    prefix: str = "",
    depth: int = 0,
    separator: str = "_",
) -> list[FieldInfo]:
    """Parse a ROS 2 IDL definition to extract field info (best effort)."""
    fields: list[FieldInfo] = []
    idl_to_ros = {
        "boolean": "bool",
        "octet": "uint8",
        "int8": "int8",
        "uint8": "uint8",
        "int16": "int16",
        "uint16": "uint16",
        "int32": "int32",
        "uint32": "uint32",
        "int64": "int64",
        "uint64": "uint64",
        "float": "float32",
        "double": "float64",
        "string": "string",
        "wstring": "string",
    }

    for line in idl_text.splitlines():
        m = _IDL_FIELD_RE.match(line)
        if not m:
            continue
        idl_type, name = m.group(1).strip(), m.group(2)
        full_name = f"{prefix}{separator}{name}" if prefix else name

        is_sequence = "sequence" in idl_type.lower()
        if is_sequence:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))
            continue

        base = idl_type.split("::")[-1].strip().lower()
        ros_type = idl_to_ros.get(base, base)

        if ros_type in NUMERIC_TYPE_MAP:
            fields.append(FieldInfo(name=full_name, type=NUMERIC_TYPE_MAP[ros_type]))
        else:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))

    return fields
