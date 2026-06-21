"""RIME bundle format: parse, validate, build, and write."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from icepi.models import (
    BUNDLE_HEADER_BYTES,
    BUNDLE_MAGIC,
    BundleHeader,
    ImagePlan,
    LayoutConfig,
)
from icepi.tools import _align_up, _ascii_slot_name, strip_bitstream_header

__all__ = [
    "parse_bundle_header",
    "validate_bundle_header",
    "render_bundle_header_lines",
    "build_bundle_bytes",
    "bundle_header_from_bytes",
    "write_bundle",
]


def parse_bundle_header(header: bytes) -> BundleHeader:
    """Decode a RIME bundle header from raw bytes."""
    if len(header) < BUNDLE_HEADER_BYTES:
        raise ValueError(
            f"bundle header requires {BUNDLE_HEADER_BYTES} bytes, got {len(header)}"
        )
    # Bundle header layout (little-endian, 512 bytes total):
    #   [0:7]    magic "ICEPIB1\0"    [8:11]   version (1)
    #   [12:15]  block_size (512)      [16:19]  manifest_bytes
    #   [20:23]  image_offset          [24:27]  image_bytes
    #   [28:31]  image_padded          [32:35]  target_address
    #   [36:39]  reserved_bytes        [40:43]  crc32
    #   [44:75]  sha256 (hex string)   [76:107] slot_name (null-padded ASCII)
    (
        magic,
        reserved,
        block_size,
        manifest_bytes,
        image_offset,
        image_bytes,
        image_padded,
        target_address,
        reserved_bytes,
        crc32,
        sha256_raw,
        slot_name_raw,
    ) = struct.unpack_from("<8sIIIIIIIII32s32s", header, 0)
    slot_name = slot_name_raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
    return BundleHeader(
        magic=magic,
        reserved=reserved,
        block_size=block_size,
        manifest_bytes=manifest_bytes,
        image_offset=image_offset,
        image_bytes=image_bytes,
        image_padded=image_padded,
        target_address=target_address,
        reserved_bytes=reserved_bytes,
        crc32=crc32,
        sha256=sha256_raw.hex(),
        slot_name=slot_name or "custom",
    )


def validate_bundle_header(header: BundleHeader) -> None:
    """Raise ``ValueError`` if the bundle header is structurally invalid."""
    if not header.valid_magic:
        raise ValueError(f"unexpected bundle magic {header.magic!r}")
    if header.block_size <= 0:
        raise ValueError("bundle block size must be positive")
    if header.image_offset < BUNDLE_HEADER_BYTES:
        raise ValueError("bundle image offset falls inside the fixed header")
    if header.image_offset % header.block_size != 0:
        raise ValueError("bundle image offset is not block-aligned")
    expected_image_offset = BUNDLE_HEADER_BYTES + _align_up(header.manifest_bytes, header.block_size)
    if header.image_offset != expected_image_offset:
        raise ValueError(
            f"bundle image offset {header.image_offset} does not match manifest padding {expected_image_offset}"
        )
    if header.image_bytes <= 0:
        raise ValueError("bundle image length must be positive")
    if header.image_padded < header.image_bytes:
        raise ValueError("bundle padded image length is smaller than the payload")
    if header.image_padded % header.block_size != 0:
        raise ValueError("bundle padded image length is not block-aligned")
    if header.reserved_bytes and header.image_padded > header.reserved_bytes:
        raise ValueError("bundle image does not fit inside the reserved byte budget")


def render_bundle_header_lines(header: BundleHeader, *, base_lba: int) -> list[str]:
    """Format a bundle header as human-readable lines."""
    status = "valid" if header.valid_magic else "invalid"
    lines = [
        f"Bundle header: {status}",
        f"Base LBA: {base_lba}",
        f"Magic: {header.magic.decode('ascii', errors='replace')}",
        f"Block size: {header.block_size}",
        f"Manifest bytes: {header.manifest_bytes} ({header.manifest_blocks} blocks)",
        f"Image offset: {header.image_offset} bytes",
        f"Image start LBA: {base_lba + header.image_start_lba}",
        f"Image bytes: {header.image_bytes}",
        f"Image padded: {header.image_padded} ({header.image_blocks} blocks)",
        f"Target address: 0x{header.target_address:06X}",
        f"Reserved bytes: {header.reserved_bytes}",
        f"CRC32: 0x{header.crc32:08X}",
        f"SHA256: {header.sha256}",
        f"Slot: {header.slot_name}",
    ]
    return lines


def build_bundle_bytes(
    plan: ImagePlan,
    *,
    layout: LayoutConfig,
    payload: bytes | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Build a complete RIME bundle (header + manifest + padded image).

    Returns ``(bundle_bytes, manifest_dict)``.
    """
    image = strip_bitstream_header(payload if payload is not None else plan.bitstream_path.read_bytes())
    if len(image) == 0:
        raise ValueError("bundle payload is empty — zero-length bitstreams cannot be installed")
    manifest = {
        "slot": plan.slot_name,
        "target_address": plan.address,
        "reserved_bytes": plan.reserved_bytes,
        "bitstream_bytes": plan.bitstream_bytes,
        "padded_bytes": plan.padded_bytes,
        "erase_bytes": plan.erase_bytes,
        "chunk_size": plan.chunk_size,
        "erase_size": plan.erase_size,
        "crc32": f"0x{plan.crc32:08X}",
        "sha256": plan.sha256,
        "bootable": plan.bootable,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    manifest_padded = _align_up(len(manifest_bytes), layout.bundle_block_size)
    image_padded = _align_up(len(image), layout.bundle_block_size)
    image_offset = BUNDLE_HEADER_BYTES + manifest_padded
    header = bytearray(BUNDLE_HEADER_BYTES)
    struct.pack_into(
        "<8sIIIIIIIII32s32s",
        header,
        0,
        BUNDLE_MAGIC,
        0,
        layout.bundle_block_size,
        len(manifest_bytes),
        image_offset,
        len(image),
        image_padded,
        plan.address,
        plan.reserved_bytes or 0,
        plan.crc32,
        bytes.fromhex(plan.sha256),
        _ascii_slot_name(plan.slot_name or "custom"),
    )
    # Assemble the bundle: fixed-size header, then manifest (null-padded
    # to block boundary), then image (0xFF-padded to block boundary).
    # 0xFF padding matches erased flash so unused bytes are harmless.
    bundle = bytes(header)
    bundle += manifest_bytes.ljust(manifest_padded, b"\x00")
    bundle += image.ljust(image_padded, b"\xFF")
    return bundle, manifest


def bundle_header_from_bytes(bundle_bytes: bytes) -> BundleHeader:
    """Parse and validate a bundle header from raw bundle bytes."""
    header = parse_bundle_header(bundle_bytes[:BUNDLE_HEADER_BYTES])
    validate_bundle_header(header)
    return header


def write_bundle(
    output_path: str | Path,
    *,
    plan: ImagePlan,
    layout: LayoutConfig,
) -> tuple[Path, dict[str, Any]]:
    """Build a bundle and write it to *output_path*.  Returns ``(path, manifest_dict)``."""
    bundle_bytes, manifest = build_bundle_bytes(plan, layout=layout)
    path = Path(output_path).resolve()
    path.write_bytes(bundle_bytes)
    return path, manifest
