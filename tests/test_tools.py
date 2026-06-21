"""Tests for icepi.tools — utility functions."""

from icepi.tools import _align_up, _ascii_slot_name, _parse_int, parse_int_value


def test_parse_int_decimal():
    assert _parse_int(42) == 42
    assert _parse_int("42") == 42


def test_parse_int_hex():
    assert _parse_int("0x100") == 256
    assert _parse_int("0xFF") == 255


def test_parse_int_value():
    assert parse_int_value("0x100000") == 0x100000
    assert parse_int_value("512") == 512


def test_align_up():
    assert _align_up(0, 16) == 0
    assert _align_up(1, 16) == 16
    assert _align_up(16, 16) == 16
    assert _align_up(17, 16) == 32
    assert _align_up(100, 65536) == 65536


def test_align_up_invalid():
    try:
        _align_up(10, 0)
        assert False, "should have raised"
    except ValueError:
        pass


def test_ascii_slot_name():
    result = _ascii_slot_name("boot")
    assert len(result) == 32
    assert result[:4] == b"boot"
    assert result[4:] == b"\x00" * 28


def test_ascii_slot_name_truncation():
    result = _ascii_slot_name("a" * 100)
    assert len(result) == 32
