"""FlatBuffers message decoder.

Unlike Protobuf/ROS decoders, there is no official ``mcap-flatbuffers-support``
package. We parse the binary FlatBuffer schema (.bfbs) stored in MCAP files
to extract table structure for field info, and decode messages using the raw
FlatBuffer binary layout.

The ``flatbuffers`` Python package provides low-level Table/Builder access
but not the reflection API needed for fully generic decoding. We implement
a minimal reflection parser for the .bfbs format.
"""

from __future__ import annotations

import logging
import struct
from typing import Any

from mcap_mcp_server.decoders.base import FieldInfo
from mcap_mcp_server.flatten import flatten_dict

logger = logging.getLogger(__name__)

try:
    import flatbuffers  # noqa: F401
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

# FlatBuffer base type constants (from reflection.fbs)
_FB_NONE = 0
_FB_UTYPE = 1
_FB_BOOL = 2
_FB_BYTE = 3
_FB_UBYTE = 4
_FB_SHORT = 5
_FB_USHORT = 6
_FB_INT = 7
_FB_UINT = 8
_FB_LONG = 9
_FB_ULONG = 10
_FB_FLOAT = 11
_FB_DOUBLE = 12
_FB_STRING = 13
_FB_VECTOR = 14
_FB_OBJ = 15
_FB_UNION = 16
_FB_ARRAY = 17

_FB_TYPE_MAP: dict[int, str] = {
    _FB_BOOL: "BOOLEAN",
    _FB_BYTE: "TINYINT",
    _FB_UBYTE: "UTINYINT",
    _FB_SHORT: "SMALLINT",
    _FB_USHORT: "USMALLINT",
    _FB_INT: "INTEGER",
    _FB_UINT: "UINTEGER",
    _FB_LONG: "BIGINT",
    _FB_ULONG: "UBIGINT",
    _FB_FLOAT: "FLOAT",
    _FB_DOUBLE: "DOUBLE",
    _FB_STRING: "VARCHAR",
}

_FB_STRUCT_SIZE: dict[int, tuple[str, int]] = {
    _FB_BOOL: ("?", 1),
    _FB_BYTE: ("b", 1),
    _FB_UBYTE: ("B", 1),
    _FB_SHORT: ("<h", 2),
    _FB_USHORT: ("<H", 2),
    _FB_INT: ("<i", 4),
    _FB_UINT: ("<I", 4),
    _FB_LONG: ("<q", 8),
    _FB_ULONG: ("<Q", 8),
    _FB_FLOAT: ("<f", 4),
    _FB_DOUBLE: ("<d", 8),
}


class FlatBufferDecoder:
    """Decode FlatBuffer-encoded MCAP messages."""

    def __init__(self, flatten_depth: int = 3) -> None:
        if not _AVAILABLE:
            raise ImportError(
                "flatbuffers is required. "
                "Install with: pip install mcap-mcp-server[flatbuffers]"
            )
        self._flatten_depth = flatten_depth
        self._schema_cache: dict[int, list[_FieldDef]] = {}

    def can_decode(self, message_encoding: str, schema_encoding: str) -> bool:
        return message_encoding == "flatbuffer" and schema_encoding == "flatbuffer"

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
        if not schema or not data:
            return {}
        try:
            field_defs = self._get_field_defs(schema, schema_id)
            raw = _decode_table(data, field_defs)
            return flatten_dict(raw, max_depth=self._flatten_depth)
        except Exception:
            logger.debug("FlatBuffer decode failed", exc_info=True)
            return {}

    def get_field_info(self, schema: bytes, schema_encoding: str) -> list[FieldInfo]:
        if schema_encoding != "flatbuffer" or not schema:
            return []
        try:
            field_defs = _parse_bfbs_schema(schema)
            return [
                FieldInfo(
                    name=fd.name,
                    type=_FB_TYPE_MAP.get(fd.base_type, "VARCHAR"),
                )
                for fd in field_defs
            ]
        except Exception:
            logger.warning("Failed to extract FlatBuffer field info", exc_info=True)
            return []

    def _get_field_defs(self, schema: bytes, schema_id: int) -> list[_FieldDef]:
        if schema_id in self._schema_cache:
            return self._schema_cache[schema_id]
        field_defs = _parse_bfbs_schema(schema)
        if schema_id:
            self._schema_cache[schema_id] = field_defs
        return field_defs


class _FieldDef:
    """Minimal field definition parsed from a .bfbs schema."""

    __slots__ = ("name", "base_type", "offset")

    def __init__(self, name: str, base_type: int, offset: int) -> None:
        self.name = name
        self.base_type = base_type
        self.offset = offset


def _parse_bfbs_schema(bfbs: bytes) -> list[_FieldDef]:
    """Best-effort parse of a .bfbs (binary FlatBuffer schema) to extract
    root table field definitions.

    The .bfbs format is itself a FlatBuffer encoding of reflection.fbs.
    We parse it manually since the Python flatbuffers package doesn't
    include pre-generated reflection code.
    """
    if len(bfbs) < 8:
        return []

    buf = bytearray(bfbs)

    try:
        root_offset = struct.unpack_from("<I", buf, 0)[0]
        schema_table_pos = root_offset

        vtable_offset = struct.unpack_from("<i", buf, schema_table_pos)[0]
        vtable_pos = schema_table_pos - vtable_offset

        vtable_size = struct.unpack_from("<H", buf, vtable_pos)[0]
        num_fields = (vtable_size - 4) // 2

        if num_fields < 1:
            return []

        objects_field_offset = struct.unpack_from("<H", buf, vtable_pos + 4)[0]
        if objects_field_offset == 0:
            return []

        objects_vec_pos = schema_table_pos + objects_field_offset
        objects_vec_offset = struct.unpack_from("<I", buf, objects_vec_pos)[0]
        objects_vec_start = objects_vec_pos + objects_vec_offset
        num_objects = struct.unpack_from("<I", buf, objects_vec_start)[0]

        if num_objects == 0:
            return []

        root_table_index = 0
        if num_fields >= 3:
            root_idx_field_offset = struct.unpack_from("<H", buf, vtable_pos + 4 + 2 * 2)[0]
            if root_idx_field_offset != 0:
                root_table_index = struct.unpack_from("<I", buf, schema_table_pos + root_idx_field_offset)[0]

        if root_table_index >= num_objects:
            root_table_index = 0

        obj_offset_pos = objects_vec_start + 4 + root_table_index * 4
        obj_offset = struct.unpack_from("<I", buf, obj_offset_pos)[0]
        obj_pos = obj_offset_pos + obj_offset

        return _parse_object_fields(buf, obj_pos)

    except (struct.error, IndexError, OverflowError):
        logger.debug("Failed to parse .bfbs schema", exc_info=True)
        return []


def _parse_object_fields(buf: bytearray, obj_pos: int) -> list[_FieldDef]:
    """Parse fields from an Object table in a .bfbs schema."""
    fields: list[_FieldDef] = []

    try:
        obj_vtable_offset = struct.unpack_from("<i", buf, obj_pos)[0]
        obj_vtable_pos = obj_pos - obj_vtable_offset
        obj_vtable_size = struct.unpack_from("<H", buf, obj_vtable_pos)[0]
        obj_num_fields = (obj_vtable_size - 4) // 2

        if obj_num_fields < 2:
            return []

        # Object.fields is at vtable index 2 (offset +8 in vtable)
        fields_field_offset = struct.unpack_from("<H", buf, obj_vtable_pos + 4 + 1 * 2)[0]
        if fields_field_offset == 0:
            return []

        fields_vec_pos = obj_pos + fields_field_offset
        fields_vec_offset = struct.unpack_from("<I", buf, fields_vec_pos)[0]
        fields_vec_start = fields_vec_pos + fields_vec_offset
        num_fields = struct.unpack_from("<I", buf, fields_vec_start)[0]

        for i in range(num_fields):
            field_offset_pos = fields_vec_start + 4 + i * 4
            field_offset = struct.unpack_from("<I", buf, field_offset_pos)[0]
            field_pos = field_offset_pos + field_offset

            field_vtable_soff = struct.unpack_from("<i", buf, field_pos)[0]
            field_vtable_pos = field_pos - field_vtable_soff
            field_vtable_size = struct.unpack_from("<H", buf, field_vtable_pos)[0]
            field_num_entries = (field_vtable_size - 4) // 2

            # Field.name is at vtable index 0
            name = ""
            if field_num_entries >= 1:
                name_off = struct.unpack_from("<H", buf, field_vtable_pos + 4)[0]
                if name_off:
                    name_str_pos = field_pos + name_off
                    name_str_offset = struct.unpack_from("<I", buf, name_str_pos)[0]
                    name_start = name_str_pos + name_str_offset
                    name_len = struct.unpack_from("<I", buf, name_start)[0]
                    name = buf[name_start + 4 : name_start + 4 + name_len].decode(
                        "utf-8", errors="replace"
                    )

            # Field.type is at vtable index 1
            base_type = _FB_STRING
            if field_num_entries >= 2:
                type_off = struct.unpack_from("<H", buf, field_vtable_pos + 4 + 1 * 2)[0]
                if type_off:
                    type_table_pos = field_pos + type_off
                    type_table_offset = struct.unpack_from("<I", buf, type_table_pos)[0]
                    type_pos = type_table_pos + type_table_offset

                    type_vtable_soff = struct.unpack_from("<i", buf, type_pos)[0]
                    type_vtable_pos = type_pos - type_vtable_soff
                    type_vtable_size = struct.unpack_from("<H", buf, type_vtable_pos)[0]
                    type_num_entries = (type_vtable_size - 4) // 2

                    if type_num_entries >= 1:
                        bt_off = struct.unpack_from("<H", buf, type_vtable_pos + 4)[0]
                        if bt_off:
                            base_type = buf[type_pos + bt_off]

            # Field.id is at vtable index 2, Field.offset is at vtable index 3
            # We need Field.offset — the byte position in the message vtable
            field_fb_offset = 0
            if field_num_entries >= 4:
                off_off = struct.unpack_from("<H", buf, field_vtable_pos + 4 + 3 * 2)[0]
                if off_off:
                    field_fb_offset = struct.unpack_from("<H", buf, field_pos + off_off)[0]
            if field_fb_offset == 0 and field_num_entries >= 3:
                # Fallback: use Field.id to compute offset
                id_off = struct.unpack_from("<H", buf, field_vtable_pos + 4 + 2 * 2)[0]
                if id_off:
                    field_id = struct.unpack_from("<H", buf, field_pos + id_off)[0]
                    field_fb_offset = 4 + field_id * 2

            if name and field_fb_offset > 0:
                fields.append(_FieldDef(name=name, base_type=base_type, offset=field_fb_offset))

    except (struct.error, IndexError, OverflowError):
        logger.debug("Failed to parse object fields from .bfbs", exc_info=True)

    return fields


def _decode_table(data: bytes, field_defs: list[_FieldDef]) -> dict[str, Any]:
    """Decode a FlatBuffer table using pre-parsed field definitions."""
    if not data or len(data) < 4:
        return {}

    buf = bytearray(data)
    root_offset = struct.unpack_from("<I", buf, 0)[0]
    table_pos = root_offset

    vtable_soffset = struct.unpack_from("<i", buf, table_pos)[0]
    vtable_pos = table_pos - vtable_soffset

    vtable_size = struct.unpack_from("<H", buf, vtable_pos)[0]

    result: dict[str, Any] = {}
    for fd in field_defs:
        if fd.offset >= vtable_size:
            result[fd.name] = None
            continue

        field_offset = struct.unpack_from("<H", buf, vtable_pos + fd.offset)[0]
        if field_offset == 0:
            result[fd.name] = None
            continue

        field_pos = table_pos + field_offset

        if fd.base_type in _FB_STRUCT_SIZE:
            fmt, size = _FB_STRUCT_SIZE[fd.base_type]
            if field_pos + size <= len(buf):
                val = struct.unpack_from(fmt, buf, field_pos)[0]
                if fd.base_type == _FB_BOOL:
                    val = bool(val)
                result[fd.name] = val
            else:
                result[fd.name] = None
        elif fd.base_type == _FB_STRING:
            try:
                str_offset = struct.unpack_from("<I", buf, field_pos)[0]
                str_start = field_pos + str_offset
                str_len = struct.unpack_from("<I", buf, str_start)[0]
                result[fd.name] = buf[str_start + 4 : str_start + 4 + str_len].decode(
                    "utf-8", errors="replace"
                )
            except (struct.error, IndexError):
                result[fd.name] = None
        else:
            result[fd.name] = None

    return result
