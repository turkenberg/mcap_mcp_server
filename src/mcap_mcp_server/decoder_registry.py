"""Pluggable decoder discovery and registration.

At startup the registry:
1. Registers the built-in JSON decoder.
2. Discovers additional decoders via the ``mcap_mcp_server.decoders`` entry-point group.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from mcap_mcp_server.decoders.json_decoder import JsonDecoder

if TYPE_CHECKING:
    from mcap_mcp_server.decoders.base import MessageDecoder

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "mcap_mcp_server.decoders"


class DecoderRegistry:
    """Registry of available message decoders."""

    def __init__(self, flatten_depth: int = 3) -> None:
        self._decoders: list[MessageDecoder] = []
        self._flatten_depth = flatten_depth
        self._register_builtins()

    def _register_builtins(self) -> None:
        self.register(JsonDecoder(flatten_depth=self._flatten_depth))
        self._try_register_optional()

    def _try_register_optional(self) -> None:
        """Auto-register optional decoders if their dependencies are installed."""
        optional_decoders = [
            ("mcap_mcp_server.decoders.protobuf_decoder", "ProtobufDecoder"),
            ("mcap_mcp_server.decoders.ros1_decoder", "Ros1Decoder"),
            ("mcap_mcp_server.decoders.ros2_decoder", "Ros2Decoder"),
            ("mcap_mcp_server.decoders.flatbuffer_decoder", "FlatBufferDecoder"),
        ]
        for module_path, class_name in optional_decoders:
            try:
                import importlib

                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                instance = cls(flatten_depth=self._flatten_depth)
                self._decoders.append(instance)
                logger.info("Registered optional decoder: %s", class_name)
            except ImportError:
                logger.debug("Optional decoder %s not available (missing dependency)", class_name)
            except Exception:
                logger.warning("Failed to register %s", class_name, exc_info=True)

    def register(self, decoder: MessageDecoder) -> None:
        self._decoders.append(decoder)

    def get_decoder(
        self, message_encoding: str, schema_encoding: str
    ) -> MessageDecoder | None:
        """Return the first decoder that can handle the given encoding pair."""
        for decoder in self._decoders:
            if decoder.can_decode(message_encoding, schema_encoding):
                return decoder
        return None

    def discover(self) -> None:
        """Load decoders registered as entry points by third-party packages."""
        group = entry_points(group=ENTRY_POINT_GROUP)

        for ep in group:
            try:
                cls = ep.load()
                instance = cls(flatten_depth=self._flatten_depth)
                if not any(type(d) is cls for d in self._decoders):
                    self.register(instance)
                    logger.info("Loaded decoder plugin: %s", ep.name)
            except Exception:
                logger.warning("Failed to load decoder entry point %s", ep.name, exc_info=True)

    @property
    def available_encodings(self) -> list[str]:
        """Human-readable list of supported encoding names (for diagnostics)."""
        names = []
        for d in self._decoders:
            names.append(type(d).__name__)
        return names
