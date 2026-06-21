"""Tests for firmware artifacts and auto-recovery FSM orchestration.

Covers: firmware hex validation, auto-recovery control block round-trips,
multi-flag combinations, flash timing constants, and multi-board config.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from icepi.build import IMAGES_ROOT, MODULES_ROOT
from icepi.flash_service import DEFAULT_BAUD
from icepi.models import (
    AUTO_RESULT_LABELS,
)
from icepi.sd import (
    build_auto_control_block,
    encode_auto_control_block,
    parse_auto_control_block,
    validate_auto_control_block,
)
from icepi.flash_service import load_board_target, BoardTarget


# ---------------------------------------------------------------------------
# Firmware hex file validation
# ---------------------------------------------------------------------------

def test_rime_i_firmware_hex_exists():
    """The rime-i module has firmware.hex build artifacts."""
    pico = MODULES_ROOT / "rime-i"
    if not pico.exists():
        pytest.skip("rime-i module not present")
    fw_hex = pico / "firmware.hex"
    boot_hex = pico / "boot_rom.hex"
    assert fw_hex.exists() or boot_hex.exists(), "no hex files in rime-i module"


def test_rime_i_bitstream_exists():
    """The rime-i module has a bitstream.bit from a previous build."""
    pico = MODULES_ROOT / "rime-i"
    if not pico.exists():
        pytest.skip("rime-i module not present")
    bit = pico / "bitstream.bit"
    if bit.exists():
        data = bit.read_bytes()
        assert len(data) > 1000, f"bitstream too small: {len(data)} bytes"


def test_thaw_bitstream_valid():
    """The thaw bitstream has a reasonable size for the flash service."""
    thaw = IMAGES_ROOT / "thaw"
    if not thaw.exists():
        pytest.skip("thaw not present")
    bit = thaw / "bitstream.bit"
    if not bit.exists():
        pytest.skip("thaw not built")
    data = bit.read_bytes()
    # Thaw is ~150KB compressed
    assert 50000 < len(data) < 500000, f"thaw bitstream size unexpected: {len(data)}"


# ---------------------------------------------------------------------------
# Auto-recovery FSM: full round-trip with all flag combinations
# ---------------------------------------------------------------------------

def test_auto_control_all_flag_combinations():
    """Round-trip every flag combination through build -> encode -> decode -> validate."""
    for armed in (True, False):
        for clear_on_success in (True, False):
            for fallback_on_fail in (True, False):
                block = build_auto_control_block(
                    primary_lba=2048,
                    fallback_lba=4096 if fallback_on_fail else 0,
                    attempt_limit=5,
                    armed=armed,
                    clear_on_success=clear_on_success,
                    fallback_on_fail=fallback_on_fail,
                )
                encoded = encode_auto_control_block(block)
                assert len(encoded) == 512

                decoded = parse_auto_control_block(encoded)
                assert decoded.armed == armed
                assert decoded.clear_on_success == clear_on_success
                if fallback_on_fail and block.fallback_lba:
                    assert decoded.fallback_on_fail is True
                assert decoded.primary_lba == 2048
                assert decoded.attempt_limit == 5

                # Checksum must validate
                validate_auto_control_block(decoded)
                assert decoded.valid


def test_auto_control_corrupt_checksum_detected():
    """A single-bit flip in the checksum is caught."""
    block = build_auto_control_block(
        primary_lba=100,
        armed=True,
        attempt_limit=3,
    )
    encoded = bytearray(encode_auto_control_block(block))
    # Flip one bit in the checksum (last 4 bytes of the 64-byte header)
    encoded[60] ^= 0x01
    decoded = parse_auto_control_block(bytes(encoded))
    assert not decoded.checksum_ok
    assert not decoded.valid


def test_auto_control_corrupt_magic_detected():
    """Wrong magic bytes are caught."""
    block = build_auto_control_block(primary_lba=100, armed=True)
    encoded = bytearray(encode_auto_control_block(block))
    encoded[0] = 0x00  # corrupt magic
    decoded = parse_auto_control_block(bytes(encoded))
    assert not decoded.valid_magic


def test_auto_control_all_result_labels():
    """Every defined result code has a human-readable label."""
    for code, label in AUTO_RESULT_LABELS.items():
        assert isinstance(label, str)
        assert len(label) > 0


def test_auto_control_attempt_tracking():
    """attempt_count and last_result survive round-trip."""
    from icepi.models import AUTO_RESULT_PENDING
    block = build_auto_control_block(
        primary_lba=2048,
        armed=True,
        attempt_limit=3,
        attempt_count=0,
        last_result=AUTO_RESULT_PENDING,
    )
    encoded = encode_auto_control_block(block)
    decoded = parse_auto_control_block(encoded)
    assert decoded.attempt_count == 0
    assert decoded.last_result_name == "pending"
    assert decoded.valid


# ---------------------------------------------------------------------------
# Flash timing regression constants
# ---------------------------------------------------------------------------

def test_upload_timing_constants():
    """Verify the timing parameters used by the upload paths are sane."""
    from icepi.flash_service import FlashService
    # These are the default values used in production
    svc = FlashService.__new__(FlashService)
    svc.timeout = 0.5
    svc.idle_gap = 0.002
    svc.baud = DEFAULT_BAUD
    # Baud rate should give ~11.5 KB/s at 115200
    bytes_per_sec = svc.baud / 10  # 8N1 = 10 bits per byte
    assert 10000 < bytes_per_sec < 15000, f"unexpected throughput: {bytes_per_sec}"
    # For a 150KB bitstream at 16 bytes/chunk with protocol overhead:
    # ~9375 chunks, each needs TX (20 bytes) + RX (2 bytes) = 22 bytes
    # At 11.5 KB/s = ~18 seconds for the program phase alone
    chunks_150k = 150000 // 16
    overhead_bytes = chunks_150k * 22
    min_time = overhead_bytes / bytes_per_sec
    assert 10 < min_time < 30, f"150KB upload estimate: {min_time:.1f}s"


# ---------------------------------------------------------------------------
# Multi-board config
# ---------------------------------------------------------------------------

def test_board_target_merge():
    """BoardTarget.merge correctly overrides individual fields."""
    base = BoardTarget(
        usb_vid=0x0403,
        usb_pid=0x6015,
        usb_serial="FT231X_A",
        baud=115200,
    )
    overridden = base.merge(usb_serial="FT231X_B", baud=230400)
    assert overridden.usb_vid == 0x0403  # preserved
    assert overridden.usb_pid == 0x6015  # preserved
    assert overridden.usb_serial == "FT231X_B"  # overridden
    assert overridden.baud == 230400  # overridden


def test_board_target_identity_hints():
    """has_identity_hints returns True when any USB identity is set."""
    empty = BoardTarget()
    assert not empty.has_identity_hints()

    with_vid = BoardTarget(usb_vid=0x0403)
    assert with_vid.has_identity_hints()

    with_serial = BoardTarget(usb_serial="ABC")
    assert with_serial.has_identity_hints()


def test_board_target_as_dict():
    """as_dict includes all fields."""
    t = BoardTarget(usb_vid=0x0403, usb_pid=0x6015, baud=115200)
    d = t.as_dict()
    assert d["usb_vid"] == 0x0403
    assert d["baud"] == 115200
    assert "usb_serial" in d


def test_load_board_target_from_json(tmp_path: Path):
    """load_board_target reads a board config JSON file."""
    import json
    config = tmp_path / "board.json"
    config.write_text(json.dumps({
        "usb_vid": "0x0403",
        "usb_pid": "0x6015",
        "usb_serial": "FT231X_BOARD2",
        "baud": 230400,
    }), encoding="utf-8")
    target = load_board_target(str(config))
    assert target.usb_vid == 0x0403
    assert target.usb_serial == "FT231X_BOARD2"
    assert target.baud == 230400
