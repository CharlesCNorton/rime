"""Tests for icepi.sd.read_sd_bytes — multi-block spanning reads."""

import pytest

from icepi.sd import read_sd_bytes


class FakeService:
    """Mock FlashService that returns LBA-tagged blocks."""

    def sd_read(self, lba: int, *, offset: int = 0, length: int = 512) -> bytes:
        block = bytes([(lba & 0xFF)] * 512)
        return block[offset : offset + length]


def test_read_zero_length():
    assert read_sd_bytes(FakeService(), lba=0, length=0) == b""


def test_read_single_block():
    data = read_sd_bytes(FakeService(), lba=5, length=512)
    assert len(data) == 512
    assert data == bytes([5] * 512)


def test_read_partial_block():
    data = read_sd_bytes(FakeService(), lba=3, offset=10, length=16)
    assert len(data) == 16
    assert data == bytes([3] * 16)


def test_read_spans_two_blocks():
    data = read_sd_bytes(FakeService(), lba=0, offset=500, length=24)
    assert len(data) == 24
    # First 12 bytes from LBA 0, next 12 from LBA 1
    assert data[:12] == bytes([0] * 12)
    assert data[12:] == bytes([1] * 12)


def test_read_negative_lba():
    with pytest.raises(ValueError):
        read_sd_bytes(FakeService(), lba=-1, length=16)


def test_read_negative_offset():
    with pytest.raises(ValueError):
        read_sd_bytes(FakeService(), lba=0, offset=-1, length=16)


def test_read_negative_length():
    with pytest.raises(ValueError):
        read_sd_bytes(FakeService(), lba=0, length=-1)
