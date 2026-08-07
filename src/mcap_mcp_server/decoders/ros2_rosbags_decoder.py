"""ROS 2 (CDR) decoder using rosbags' C-backed deserializer.

For schemas the rosbags parser rejects, falls back per-schema to the
mcap_ros2-based Ros2Decoder.
"""
from __future__ import annotations

import logging
from dataclasses import fields, is_dataclass
from typing import Any, Callable

from mcap_mcp_server.decoders.base import FieldInfo
from mcap_mcp_server.decoders.ros2_decoder import Ros2Decoder
from mcap_mcp_server.flatten import flatten_dict

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from rosbags.typesys import Stores, get_types_from_idl, get_types_from_msg, get_typestore

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


class Ros2RosbagsDecoder:
    """Decode ROS 2 CDR-encoded MCAP messages using rosbags."""

    def __init__(self, flatten_depth: int = 3) -> None:
        if not _AVAILABLE:
            raise ImportError(
                "rosbags is required. Install with: pip install mcap-mcp-server[ros2]"
            )
        self._flatten_depth = flatten_depth
        self._store = get_typestore(Stores.LATEST)
        # schema_id -> bound decode function (rosbags or fallback). None until first message.
        self._decoders: dict[int, Callable[[bytes, str], dict[str, Any]]] = {}
        self._fallback: Ros2Decoder | None = None

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
        fn = self._decoders.get(schema_id)
        if fn is None:
            fn = self._prepare(schema, schema_name, schema_encoding, schema_id)
            self._decoders[schema_id] = fn
        return fn(data, schema_name)

    def get_field_info(self, schema: bytes, schema_encoding: str) -> list[FieldInfo]:
        return self._get_fallback().get_field_info(schema, schema_encoding)

    def _prepare(
        self, schema_data: bytes, schema_name: str, schema_encoding: str, schema_id: int
    ) -> Callable[[bytes, str], dict[str, Any]]:
        if self._register(schema_data, schema_name, schema_encoding):
            return self._rosbags_decode
        return self._make_fallback_decode(schema_data, schema_encoding, schema_id)

    def _register(self, schema_data: bytes, schema_name: str, schema_encoding: str) -> bool:
        try:
            text = schema_data.decode("utf-8")
            if schema_encoding == "ros2msg":
                types = get_types_from_msg(text, schema_name)
            elif schema_encoding == "ros2idl":
                types = get_types_from_idl(text)
            else:
                return False
            self._store.register(types)
            return True
        except Exception:
            logger.debug(
                "rosbags could not register schema %s; using mcap_ros2 fallback",
                schema_name,
                exc_info=True,
            )
            return False

    def _rosbags_decode(self, data: bytes, schema_name: str) -> dict[str, Any]:
        msg = self._store.deserialize_cdr(data, schema_name)
        return flatten_dict(_to_dict(msg), max_depth=self._flatten_depth)

    def _make_fallback_decode(
        self, schema_data: bytes, schema_encoding: str, schema_id: int
    ) -> Callable[[bytes, str], dict[str, Any]]:
        fallback = self._get_fallback()

        def decode(data: bytes, schema_name: str) -> dict[str, Any]:
            return fallback.decode(
                schema_data,
                data,
                schema_name=schema_name,
                schema_encoding=schema_encoding,
                schema_id=schema_id,
            )

        return decode

    def _get_fallback(self) -> Ros2Decoder:
        if self._fallback is None:
            self._fallback = Ros2Decoder(flatten_depth=self._flatten_depth)
        return self._fallback


_FIELD_CACHE: dict[type, tuple[str, ...]] = {}


def _field_names(t: type) -> tuple[str, ...] | None:
    """Return cached field-name tuple for a dataclass type, or None if not a dataclass."""
    if t in _FIELD_CACHE:
        return _FIELD_CACHE[t]
    if not is_dataclass(t):
        return None
    names = tuple(f.name for f in fields(t))
    _FIELD_CACHE[t] = names
    return names


def _to_dict(obj: Any) -> Any:
    """Convert a rosbags-decoded message (dataclass tree) to a plain dict.

    numpy arrays pass through unchanged — orjson serialises them natively,
    avoiding a costly .tolist().
    """
    names = _field_names(type(obj))
    if names is not None:
        return {n: _to_dict(getattr(obj, n)) for n in names}
    if _AVAILABLE and isinstance(obj, np.ndarray):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    return obj
