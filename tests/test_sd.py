"""Tests for icepi.sd — partitions, auto-control, staging logic."""

import struct

from icepi.sd import (
    SdPartitionEntry,
    build_auto_control_block,
    encode_auto_control_block,
    find_sd_staging_lba,
    parse_auto_control_block,
    parse_sd_partitions,
    sd_gaps_from_partitions,
    validate_auto_control_block,
)


def _make_mbr(partitions: list[tuple[int, int, int]] | None = None) -> bytes:
    """Build a minimal MBR. partitions = [(type, first_lba, sectors), ...]"""
    block = bytearray(512)
    block[510] = 0x55
    block[511] = 0xAA
    for i, (ptype, first_lba, sectors) in enumerate(partitions or []):
        offset = 446 + (i * 16)
        block[offset] = 0x00  # status
        block[offset + 4] = ptype
        struct.pack_into("<I", block, offset + 8, first_lba)
        struct.pack_into("<I", block, offset + 12, sectors)
    return bytes(block)


def test_parse_sd_partitions_empty():
    mbr = _make_mbr()
    parts = parse_sd_partitions(mbr)
    assert len(parts) == 0


def test_parse_sd_partitions_one():
    mbr = _make_mbr([(0x0C, 2048, 100000)])
    parts = parse_sd_partitions(mbr)
    assert len(parts) == 1
    assert parts[0].type_code == 0x0C
    assert parts[0].first_lba == 2048
    assert parts[0].sectors == 100000


def test_sd_gaps_from_partitions():
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 2048, 100000),
        SdPartitionEntry(1, 0x00, 0x00, 0, 0),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    gaps = sd_gaps_from_partitions(parts)
    assert len(gaps) == 1
    assert gaps[0] == (1, 2047)


def test_find_sd_staging_lba_aligned():
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 8192, 100000),
        SdPartitionEntry(1, 0x00, 0x00, 0, 0),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    lba = find_sd_staging_lba(parts, required_blocks=10)
    assert lba == 2048  # aligned to 2048


def test_find_sd_staging_lba_explicit():
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 8192, 100000),
        SdPartitionEntry(1, 0x00, 0x00, 0, 0),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    lba = find_sd_staging_lba(parts, required_blocks=10, lba=100)
    assert lba == 100


def test_find_sd_staging_lba_too_small():
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 4, 100000),
        SdPartitionEntry(1, 0x00, 0x00, 0, 0),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    try:
        find_sd_staging_lba(parts, required_blocks=10)
        assert False, "should have raised"
    except ValueError:
        pass


def test_auto_control_block_roundtrip():
    block = build_auto_control_block(
        primary_lba=2048,
        attempt_limit=3,
        armed=True,
        clear_on_success=True,
    )
    assert block.valid
    assert block.armed
    raw = encode_auto_control_block(block)
    assert len(raw) == 512
    parsed = parse_auto_control_block(raw, lba=1)
    assert parsed.valid
    assert parsed.armed
    assert parsed.primary_lba == 2048
    assert parsed.attempt_limit == 3
    validate_auto_control_block(parsed)  # should not raise


def test_find_sd_staging_lba_guards_control_lba():
    """find_sd_staging_lba must never return AUTO_CONTROL_LBA (1), even
    when the caller does not pass reserved_ranges."""
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 8192, 100000),
        SdPartitionEntry(1, 0x00, 0x00, 0, 0),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    lba = find_sd_staging_lba(parts, required_blocks=1)
    assert lba != 1, "staging must not overlap auto-recovery control LBA"

    lba2 = find_sd_staging_lba(parts, required_blocks=1, align_blocks=1)
    assert lba2 != 1

    try:
        find_sd_staging_lba(parts, required_blocks=1, lba=1)
        assert False, "explicit LBA 1 should be rejected"
    except ValueError:
        pass


def test_auto_control_block_corrupt():
    block = build_auto_control_block(armed=True)
    raw = bytearray(encode_auto_control_block(block))
    raw[0] = 0xFF  # corrupt magic
    parsed = parse_auto_control_block(bytes(raw), lba=1)
    assert not parsed.valid
    try:
        validate_auto_control_block(parsed)
        assert False, "should have raised"
    except ValueError:
        pass
