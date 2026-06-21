"""Edge-case tests for layout, bundle, and SD operations."""

import pytest
import struct
from hypothesis import given, settings
from hypothesis import strategies as st

from icepi.layout import load_layout, plan_image
from icepi.bundle import validate_bundle_header, parse_bundle_header
from icepi.models import BUNDLE_HEADER_BYTES, BUNDLE_MAGIC
from icepi.sd import parse_sd_partitions, find_sd_staging_lba, SdPartitionEntry
from icepi.tools import _align_up
from icepi.flash_service import crc8


# ---------------------------------------------------------------------------
# Layout edge cases
# ---------------------------------------------------------------------------

def test_plan_image_empty_bitstream(tmp_path):
    layout = load_layout()
    empty = tmp_path / "empty.bit"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        plan_image(empty, layout=layout)


def test_plan_image_unaligned_address(tmp_path):
    layout = load_layout()
    bit = tmp_path / "test.bit"
    bit.write_bytes(b"\xFF" * 16)
    with pytest.raises(ValueError, match="not aligned"):
        plan_image(bit, layout=layout, address=0x100)  # not 64K aligned


def test_plan_image_too_large(tmp_path):
    layout = load_layout()
    # Create a bitstream larger than the boot slot (1 MiB)
    bit = tmp_path / "huge.bit"
    bit.write_bytes(b"\xFF" * (1048576 + 16))
    with pytest.raises(ValueError, match="reserves"):
        plan_image(bit, layout=layout, slot_name="boot")


# ---------------------------------------------------------------------------
# Bundle header edge cases
# ---------------------------------------------------------------------------

def test_bundle_header_too_short():
    with pytest.raises(ValueError, match="requires"):
        parse_bundle_header(b"\x00" * 100)


def test_bundle_header_bad_magic():
    header = bytearray(BUNDLE_HEADER_BYTES)
    header[0:8] = b"BADMAGIC"
    parsed = parse_bundle_header(bytes(header))
    with pytest.raises(ValueError, match="magic"):
        validate_bundle_header(parsed)


def test_bundle_header_zero_block_size():
    header = bytearray(BUNDLE_HEADER_BYTES)
    struct.pack_into("<8sI", header, 0, BUNDLE_MAGIC, 0)
    # block_size = 0
    struct.pack_into("<I", header, 12, 0)
    parsed = parse_bundle_header(bytes(header))
    with pytest.raises(ValueError, match="block size"):
        validate_bundle_header(parsed)


# ---------------------------------------------------------------------------
# SD partition edge cases
# ---------------------------------------------------------------------------

def test_parse_sd_partitions_no_signature():
    block = bytearray(512)
    # No 0x55AA signature
    with pytest.raises(ValueError, match="MBR signature"):
        parse_sd_partitions(bytes(block))


def test_parse_sd_partitions_short_block():
    with pytest.raises(ValueError, match="512"):
        parse_sd_partitions(b"\x00" * 100)


def test_sd_gaps_two_partitions():
    """Two partitions with a gap between them."""
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 100, 50),
        SdPartitionEntry(1, 0x00, 0x0C, 200, 100),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    from icepi.sd import sd_gaps_from_partitions
    gaps = sd_gaps_from_partitions(parts)
    assert (1, 99) in gaps      # before first partition
    assert (150, 199) in gaps   # between partitions


def test_staging_lba_respects_reserved_ranges():
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 8192, 100000),
        SdPartitionEntry(1, 0x00, 0x00, 0, 0),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    # Reserve the default aligned position (2048) so it has to find another spot
    lba = find_sd_staging_lba(
        parts,
        required_blocks=10,
        reserved_ranges=[(2048, 2100)],
    )
    assert lba >= 2101 or lba < 2048


def test_staging_lba_zero_blocks_raises():
    parts = [
        SdPartitionEntry(0, 0x00, 0x0C, 8192, 100000),
        SdPartitionEntry(1, 0x00, 0x00, 0, 0),
        SdPartitionEntry(2, 0x00, 0x00, 0, 0),
        SdPartitionEntry(3, 0x00, 0x00, 0, 0),
    ]
    with pytest.raises(ValueError, match="positive"):
        find_sd_staging_lba(parts, required_blocks=0)


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis)
# ---------------------------------------------------------------------------


@given(data=st.binary(min_size=0, max_size=256))
@settings()
def test_crc8_deterministic(data):
    """CRC8 of the same input is always the same."""
    assert crc8(data) == crc8(data)


@given(data=st.binary(min_size=1, max_size=256))
@settings()
def test_crc8_within_range(data):
    """CRC8 always returns a value in [0, 255]."""
    result = crc8(data)
    assert 0 <= result <= 255


@given(data=st.binary(min_size=1, max_size=256))
@settings()
def test_crc8_detects_single_bit_flip(data):
    """Flipping any single bit in the input changes the CRC."""
    original = crc8(data)
    for byte_idx in range(len(data)):
        for bit_idx in range(8):
            corrupted = bytearray(data)
            corrupted[byte_idx] ^= 1 << bit_idx
            assert crc8(bytes(corrupted)) != original or corrupted == bytearray(data)


@given(value=st.integers(min_value=1, max_value=1048576),
       alignment=st.integers(min_value=1, max_value=65536))
@settings()
def test_align_up_properties(value, alignment):
    """align_up result is >= value, divisible by alignment, and minimal."""
    result = _align_up(value, alignment)
    assert result >= value
    assert result % alignment == 0
    assert result - alignment < value


@given(
    first_lba=st.integers(min_value=100, max_value=100000),
    sectors=st.integers(min_value=1, max_value=100000),
)
@settings()
def test_sd_partition_entry_properties(first_lba, sectors):
    """SdPartitionEntry maintains consistent derived properties."""
    entry = SdPartitionEntry(0, 0x80, 0x0C, first_lba, sectors)
    assert entry.present
    assert entry.bootable
    assert entry.last_lba == first_lba + sectors - 1
    assert entry.bytes == sectors * 512
