"""ROS 1 message decoder wrapping mcap-ros1-support."""

from __future__ import annotations

import logging
import re
from typing import Any

from mcap_mcp_server.decoders.base import NUMERIC_TYPE_MAP, FieldInfo
from mcap_mcp_server.flatten import flatten_dict

logger = logging.getLogger(__name__)

try:
    from mcap.records import Schema
    from mcap_ros1.decoder import DecoderFactory

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


class Ros1Decoder:
    """Decode ROS 1 encoded MCAP messages using mcap-ros1-support."""

    def __init__(self, flatten_depth: int = 3) -> None:
        if not _AVAILABLE:
            raise ImportError(
                "mcap-ros1-support is required. "
                "Install with: pip install mcap-mcp-server[ros1]"
            )
        self._flatten_depth = flatten_depth
        self._factory = DecoderFactory()
        self._decoders: dict[int, Any] = {}

    def can_decode(self, message_encoding: str, schema_encoding: str) -> bool:
        return message_encoding == "ros1" and schema_encoding == "ros1msg"

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
        raw = _ros_msg_to_dict(msg)
        return flatten_dict(raw, max_depth=self._flatten_depth)

    def get_field_info(self, schema: bytes, schema_encoding: str) -> list[FieldInfo]:
        if schema_encoding != "ros1msg" or not schema:
            return []
        try:
            return _parse_ros_msg_def(schema.decode("utf-8"), self._flatten_depth)
        except Exception:
            logger.warning("Failed to extract ROS1 field info", exc_info=True)
            return []

    def _get_decoder(
        self, schema_data: bytes, schema_name: str, schema_encoding: str, schema_id: int
    ) -> Any:
        if schema_id in self._decoders:
            return self._decoders[schema_id]
        schema_rec = Schema(
            id=schema_id, data=schema_data, encoding=schema_encoding, name=schema_name
        )
        decoder_fn = self._factory.decoder_for("ros1", schema_rec)
        if decoder_fn is not None:
            self._decoders[schema_id] = decoder_fn
        return decoder_fn


def _ros_msg_to_dict(msg: Any) -> dict[str, Any]:
    """Convert a ROS 1 message object to a plain dict recursively."""
    result: dict[str, Any] = {}
    slots = getattr(msg, "__slots__", [])
    for slot in slots:
        attr_name = slot.lstrip("_")
        value = getattr(msg, slot, None)
        if hasattr(value, "__slots__") and not isinstance(value, (str, bytes)):
            result[attr_name] = _ros_msg_to_dict(value)
        elif isinstance(value, (list, tuple)):
            if value and hasattr(value[0], "__slots__"):
                result[attr_name] = [_ros_msg_to_dict(v) for v in value]
            else:
                result[attr_name] = list(value)
        else:
            result[attr_name] = value
    return result


_FIELD_RE = re.compile(r"^\s*(\w[\w/]*)\s+(\w+)\s*(?:=.*)?$")


def _parse_ros_msg_def(
    msg_def: str,
    max_depth: int,
    prefix: str = "",
    depth: int = 0,
    separator: str = "_",
) -> list[FieldInfo]:
    """Parse a ROS .msg definition string to extract flattened field info.

    Only parses the top-level message (stops at the first ``===`` separator).
    """
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

        is_array = ros_type.endswith("[]")
        base_type = ros_type.rstrip("[]")

        if is_array:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))
        elif base_type in NUMERIC_TYPE_MAP:
            fields.append(FieldInfo(name=full_name, type=NUMERIC_TYPE_MAP[base_type]))
        elif "/" in base_type or base_type[0].isupper():
            if depth < max_depth - 1:
                fields.append(FieldInfo(name=full_name, type="VARCHAR"))
            else:
                fields.append(FieldInfo(name=full_name, type="VARCHAR"))
        else:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))

    return fields
