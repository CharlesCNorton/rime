"""Tests for icepi.models — dataclasses, constants, checksum."""

from icepi.models import (
    AUTO_FLAG_ARMED,
    AUTO_FLAG_CLEAR_ON_SUCCESS,
    AUTO_MAGIC,
    AUTO_RESULT_PENDING,
    BUNDLE_MAGIC,
    AutoControlBlock,
    BundleHeader,
    FlashSlot,
    LayoutConfig,
    ResolvedBitstream,
    compute_auto_control_checksum,
)
from pathlib import Path


def test_flash_slot_end():
    slot = FlashSlot(name="boot", offset=0, size=0x100000)
    assert slot.end == 0x100000


def test_flash_slot_fits():
    slot = FlashSlot(name="boot", offset=0, size=1024)
    assert slot.fits(512)
    assert slot.fits(1024)
    assert not slot.fits(1025)


def test_layout_resolve_slot():
    boot = FlashSlot(name="boot", offset=0, size=0x100000, bootable=True)
    layout = LayoutConfig(
        path=Path("test.json"),
        flash_size=0x1000000,
        default_slot="boot",
        bundle_block_size=512,
        slots={"boot": boot},
        aliases={"boot": "boot", "primary": "boot", "resident": "boot"},
    )
    assert layout.resolve_slot("boot") is boot
    assert layout.resolve_slot("primary") is boot
    assert layout.resolve_slot("resident") is boot
    assert layout.resolve_slot() is boot  # default


def test_layout_resolve_unknown_raises():
    layout = LayoutConfig(
        path=Path("test.json"),
        flash_size=0x1000000,
        default_slot="boot",
        bundle_block_size=512,
        slots={"boot": FlashSlot(name="boot", offset=0, size=0x100000)},
        aliases={"boot": "boot"},
    )
    try:
        layout.resolve_slot("nonexistent")
        assert False, "should have raised KeyError"
    except KeyError:
        pass


def test_auto_control_checksum_roundtrip():
    block = AutoControlBlock(
        magic=AUTO_MAGIC,
        reserved=0,
        flags=AUTO_FLAG_ARMED | AUTO_FLAG_CLEAR_ON_SUCCESS,
        primary_lba=2048,
        fallback_lba=0,
        attempt_limit=3,
        attempt_count=0,
        last_result=AUTO_RESULT_PENDING,
        last_error_code=0,
        last_error_detail=0,
        last_source_lba=0,
        last_bundle_crc32=0xDEADBEEF,
        aux0=0,
        aux1=0,
        checksum=0,
    )
    block.checksum = compute_auto_control_checksum(block)
    assert block.checksum_ok
    assert block.valid_magic
    assert block.valid
    assert block.armed
    assert block.clear_on_success


def test_auto_control_bad_checksum():
    block = AutoControlBlock(
        magic=AUTO_MAGIC,
        reserved=0,
        flags=0,
        primary_lba=0,
        fallback_lba=0,
        attempt_limit=0,
        attempt_count=0,
        last_result=0,
        last_error_code=0,
        last_error_detail=0,
        last_source_lba=0,
        last_bundle_crc32=0,
        aux0=0,
        aux1=0,
        checksum=0xBADBAD,
    )
    assert not block.checksum_ok
    assert not block.valid


def test_bundle_header_properties():
    header = BundleHeader(
        magic=BUNDLE_MAGIC,
        reserved=0,
        block_size=512,
        manifest_bytes=100,
        image_offset=1024,
        image_bytes=50000,
        image_padded=50176,
        target_address=0,
        reserved_bytes=0x100000,
        crc32=0x12345678,
        sha256="a" * 64,
        slot_name="boot",
    )
    assert header.valid_magic
    assert header.image_blocks == 50176 // 512
    assert header.image_start_lba == 1024 // 512


def test_resolved_bitstream_label():
    r = ResolvedBitstream(spec="rime", bitstream=Path("test.bit"), project="rime", built=True)
    assert "rime" in r.label
    r2 = ResolvedBitstream(spec="test.bit", bitstream=Path("test.bit"), project=None, built=False)
    assert "test.bit" in r2.label
