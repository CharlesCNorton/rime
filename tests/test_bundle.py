"""Tests for icepi.bundle — bundle header parse/validate/build."""

import struct

from icepi.bundle import (
    parse_bundle_header,
    validate_bundle_header,
)
from icepi.models import BUNDLE_HEADER_BYTES, BUNDLE_MAGIC, LayoutConfig, FlashSlot
from icepi.tools import _ascii_slot_name
from pathlib import Path


def _make_test_layout() -> LayoutConfig:
    boot = FlashSlot(name="boot", offset=0, size=0x100000, bootable=True)
    return LayoutConfig(
        path=Path("test.json"),
        flash_size=0x1000000,
        default_slot="boot",
        bundle_block_size=512,
        slots={"boot": boot},
        aliases={"boot": "boot"},
    )


def _make_test_header_bytes(
    *,
    magic=BUNDLE_MAGIC,
    reserved=0,
    block_size=512,
    manifest_bytes=64,
    image_bytes=1024,
    target_address=0,
    reserved_bytes=0x100000,
) -> bytes:
    manifest_padded = ((manifest_bytes + block_size - 1) // block_size) * block_size
    image_padded = ((image_bytes + block_size - 1) // block_size) * block_size
    image_offset = BUNDLE_HEADER_BYTES + manifest_padded
    header = bytearray(BUNDLE_HEADER_BYTES)
    struct.pack_into(
        "<8sIIIIIIIII32s32s",
        header, 0,
        magic, reserved, block_size, manifest_bytes,
        image_offset, image_bytes, image_padded,
        target_address, reserved_bytes, 0x12345678,
        b"\x00" * 32, _ascii_slot_name("boot"),
    )
    return bytes(header)


def test_parse_bundle_header():
    raw = _make_test_header_bytes()
    header = parse_bundle_header(raw)
    assert header.valid_magic
    assert header.image_bytes == 1024
    assert header.slot_name == "boot"


def test_validate_bundle_header_valid():
    raw = _make_test_header_bytes()
    header = parse_bundle_header(raw)
    validate_bundle_header(header)  # should not raise


def test_validate_bundle_header_bad_magic():
    raw = _make_test_header_bytes(magic=b"BADMAGIC")
    header = parse_bundle_header(raw)
    try:
        validate_bundle_header(header)
        assert False, "should have raised"
    except ValueError as exc:
        assert "magic" in str(exc).lower()


def test_validate_bundle_header_zero_image():
    raw = _make_test_header_bytes(image_bytes=0)
    header = parse_bundle_header(raw)
    try:
        validate_bundle_header(header)
        assert False, "should have raised"
    except ValueError as exc:
        assert "image" in str(exc).lower()
