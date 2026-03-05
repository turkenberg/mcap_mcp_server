# Decoders

The server uses a pluggable decoder system to support any MCAP message encoding. Decoders are resolved at load time by matching the channel's `(message_encoding, schema_encoding)` pair.

## Supported encodings

| Encoding | Schema encoding | Install extra | Decoder |
|----------|----------------|---------------|---------|
| `json` | `jsonschema` | *(built-in)* | `JsonDecoder` |
| `protobuf` | `protobuf` | `[protobuf]` | `ProtobufDecoder` |
| `ros1msg` | `ros1msg` | `[ros1]` | `Ros1Decoder` |
| `cdr` | `ros2msg` / `ros2idl` | `[ros2]` | `Ros2Decoder` |
| `flatbuffer` | `flatbuffer` | `[flatbuffers]` | `FlatBufferDecoder` |

Install all decoders with `pip install mcap-mcp-server[all]`.

## Decoder protocol

Every decoder implements three methods:

| Method | Purpose |
|--------|---------|
| `can_decode(message_encoding, schema_encoding)` | Returns `True` if this decoder handles the encoding pair |
| `decode(schema, data, **kwargs)` | Decodes raw message bytes into a flat `dict[str, Any]` |
| `get_field_info(schema, schema_encoding)` | Extracts field names and DuckDB types from the schema definition |

## Type mapping

Fields are mapped to DuckDB column types based on the source schema. JSON fields use JSON Schema types; binary encodings use native type information.

| Source type | DuckDB type |
|-------------|-------------|
| bool | BOOLEAN |
| int8 | TINYINT |
| uint8 / byte / char | UTINYINT |
| int16 | SMALLINT |
| uint16 | USMALLINT |
| int32 / int | INTEGER |
| uint32 | UINTEGER |
| int64 / long | BIGINT |
| uint64 | UBIGINT |
| float / float32 | FLOAT |
| double / float64 | DOUBLE |
| string | VARCHAR |
| bytes | BLOB |
| time / duration | BIGINT |
| array / repeated | VARCHAR (JSON-serialized) |
| nested message | Flattened with `_` separator up to `flatten_depth` |

## Discovery

At startup, the `DecoderRegistry`:

1. Registers the built-in `JsonDecoder`
2. Attempts to import each optional decoder (Protobuf, ROS1, ROS2, FlatBuffer) and registers those whose dependencies are installed
3. Loads any third-party decoders registered via the `mcap_mcp_server.decoders` entry-point group

## Custom decoders

Third-party packages can register decoders via entry points in their `pyproject.toml`:

```toml
[project.entry-points."mcap_mcp_server.decoders"]
my_encoding = "my_package:MyDecoder"
```

The class must implement the `MessageDecoder` protocol defined in `decoders/base.py`.
