"""Protobuf message decoder wrapping mcap-protobuf-support."""

from __future__ import annotations

import logging
from typing import Any

from mcap_mcp_server.decoders.base import FieldInfo
from mcap_mcp_server.flatten import flatten_dict

logger = logging.getLogger(__name__)

try:
    from google.protobuf.descriptor import FieldDescriptor
    from google.protobuf.descriptor_pool import DescriptorPool
    from google.protobuf.descriptor_pb2 import FileDescriptorSet
    from google.protobuf.json_format import MessageToDict
    from mcap.records import Schema
    from mcap_protobuf.decoder import DecoderFactory

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_PB_TYPE_MAP: dict[int, str] = {}
if _AVAILABLE:
    _PB_TYPE_MAP = {
        FieldDescriptor.TYPE_BOOL: "BOOLEAN",
        FieldDescriptor.TYPE_BYTES: "BLOB",
        FieldDescriptor.TYPE_DOUBLE: "DOUBLE",
        FieldDescriptor.TYPE_ENUM: "VARCHAR",
        FieldDescriptor.TYPE_FIXED32: "UINTEGER",
        FieldDescriptor.TYPE_FIXED64: "UBIGINT",
        FieldDescriptor.TYPE_FLOAT: "FLOAT",
        FieldDescriptor.TYPE_INT32: "INTEGER",
        FieldDescriptor.TYPE_INT64: "BIGINT",
        FieldDescriptor.TYPE_SFIXED32: "INTEGER",
        FieldDescriptor.TYPE_SFIXED64: "BIGINT",
        FieldDescriptor.TYPE_SINT32: "INTEGER",
        FieldDescriptor.TYPE_SINT64: "BIGINT",
        FieldDescriptor.TYPE_STRING: "VARCHAR",
        FieldDescriptor.TYPE_UINT32: "UINTEGER",
        FieldDescriptor.TYPE_UINT64: "UBIGINT",
    }


class ProtobufDecoder:
    """Decode Protobuf-encoded MCAP messages using mcap-protobuf-support."""

    def __init__(self, flatten_depth: int = 3) -> None:
        if not _AVAILABLE:
            raise ImportError(
                "mcap-protobuf-support and protobuf are required. "
                "Install with: pip install mcap-mcp-server[protobuf]"
            )
        self._flatten_depth = flatten_depth
        self._factory = DecoderFactory()
        self._decoders: dict[int, Any] = {}

    def can_decode(self, message_encoding: str, schema_encoding: str) -> bool:
        return message_encoding == "protobuf" and schema_encoding == "protobuf"

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
        raw = MessageToDict(msg, preserving_proto_field_name=True)
        return flatten_dict(raw, max_depth=self._flatten_depth)

    def get_field_info(self, schema: bytes, schema_encoding: str) -> list[FieldInfo]:
        if schema_encoding != "protobuf" or not schema:
            return []
        try:
            return _extract_protobuf_fields(schema, self._flatten_depth)
        except Exception:
            logger.warning("Failed to extract Protobuf field info", exc_info=True)
            return []

    def _get_decoder(
        self, schema_data: bytes, schema_name: str, schema_encoding: str, schema_id: int
    ) -> Any:
        if schema_id in self._decoders:
            return self._decoders[schema_id]
        schema_rec = Schema(
            id=schema_id, data=schema_data, encoding=schema_encoding, name=schema_name
        )
        decoder_fn = self._factory.decoder_for("protobuf", schema_rec)
        if decoder_fn is not None:
            self._decoders[schema_id] = decoder_fn
        return decoder_fn


def _extract_protobuf_fields(
    schema_data: bytes,
    max_depth: int,
    prefix: str = "",
    depth: int = 0,
    separator: str = "_",
) -> list[FieldInfo]:
    """Parse a FileDescriptorSet to extract flattened field info."""
    fds = FileDescriptorSet.FromString(schema_data)
    pool = DescriptorPool()
    for fd in fds.file:
        pool.Add(fd)

    fields: list[FieldInfo] = []
    if fds.file:
        last_file = fds.file[-1]
        if last_file.message_type:
            msg_name = f"{last_file.package}.{last_file.message_type[0].name}" if last_file.package else last_file.message_type[0].name
            try:
                descriptor = pool.FindMessageTypeByName(msg_name)
                _walk_pb_descriptor(descriptor, fields, max_depth, prefix, depth, separator)
            except KeyError:
                pass
    return fields


def _walk_pb_descriptor(descriptor: Any, fields: list[FieldInfo], max_depth: int, prefix: str, depth: int, separator: str) -> None:
    for field in descriptor.fields:
        full_name = f"{prefix}{separator}{field.name}" if prefix else field.name
        label = getattr(field, "label", None)
        if label == FieldDescriptor.LABEL_REPEATED:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))
        elif field.type == FieldDescriptor.TYPE_MESSAGE and depth < max_depth - 1:
            _walk_pb_descriptor(
                field.message_type, fields, max_depth, full_name, depth + 1, separator
            )
        elif field.type == FieldDescriptor.TYPE_MESSAGE:
            fields.append(FieldInfo(name=full_name, type="VARCHAR"))
        else:
            duckdb_type = _PB_TYPE_MAP.get(field.type, "VARCHAR")
            fields.append(FieldInfo(name=full_name, type=duckdb_type))
