"""Integration tests for higher-level RIME operations.

Tests the upload orchestration, resolve_bitstream_target branches,
SD write recovery, and bundle staging verification failure path —
all with mocked serial.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from icepi.build import resolve_bitstream_target, IMAGES_ROOT
from icepi.flash_service import (
    CMD_ERASE64,
    CMD_HELLO,
    FlashService,
    FlashServiceTimeout,
    MODE_SERVICE,
    PING_REPLY,
    crc8,
)
from icepi.layout import load_layout, plan_image
from icepi.sd import write_sd_block_with_recovery


# ---------------------------------------------------------------------------
# Item 15: upload orchestration (erase -> program -> verify)
# ---------------------------------------------------------------------------


def _frame(payload: bytes, ftype: int = 0x01) -> bytes:
    """Wrap *payload* in the length-prefixed response frame the firmware emits."""
    body = bytes([ftype, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]) + payload
    return body + bytes([crc8(body)])


class FakeSerial:
    """Serial mock: queues one response per write(), serves bytes on read()."""

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = [_frame(r) for r in responses]
        self._idx = 0
        self._buf = bytearray()
        self.written: list[bytes] = []
        self.dtr = False
        self.rts = False

    @property
    def in_waiting(self) -> int:
        return len(self._buf)

    def write(self, data: bytes) -> int:
        self.written.append(bytes(data))
        if self._idx < len(self._responses):
            self._buf.extend(self._responses[self._idx])
            self._idx += 1
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, size: int = 1) -> bytes:
        chunk = bytes(self._buf[:size])
        self._buf = self._buf[size:]
        return chunk

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SDRAM staged upload path (the only path; direct per-chunk was removed)
# ---------------------------------------------------------------------------


def test_upload_bitstream_staged(tmp_path: Path) -> None:
    """Verify staged upload: assert_service, info, sdram_write_stream, sdram_to_flash, sdram_verify_flash."""
    from icepi.flash_service import (
        CMD_INFO,
        CMD_SDRAM_WRITE_STREAM,
        CMD_SDRAM_TO_FLASH,
        CMD_SDRAM_VERIFY_FLASH,
    )

    bitstream = tmp_path / "staged.bit"
    bitstream.write_bytes(b"\xCD" * 48)  # 3 chunks of 16

    svc = FlashService.__new__(FlashService)
    svc.port_name = "MOCK"
    svc.baud = 115200
    svc.timeout = 0.5
    svc.idle_gap = 0.002
    svc.trace = False
    svc.logger = None
    svc._erase_cmd = CMD_ERASE64
    svc._info_cache = None
    svc._sd_crc32_supported = None
    svc._sd_crc32_range_supported = None
    svc._seq = 0

    responses = [
        # mode -> service
        bytes([CMD_HELLO, MODE_SERVICE]),
        # info
        bytes([CMD_INFO, 0x7F, 0xFF, 16, 16, 16, 8, 3]),
        # sdram_write_stream ack (1 block for 48 bytes padded to 4096-aligned -> 1 stream call)
        bytes([CMD_SDRAM_WRITE_STREAM, PING_REPLY]),
        # sdram_to_flash ack
        bytes([CMD_SDRAM_TO_FLASH, PING_REPLY]),
        # sdram_verify_flash ack
        bytes([CMD_SDRAM_VERIFY_FLASH, PING_REPLY]),
    ]

    svc._serial = FakeSerial(responses)

    result = svc.upload_bitstream_staged(
        bitstream,
        base_address=0,
        verify=True,
    )
    assert result.bytes == 48
    assert result.base_address == 0


def test_upload_bitstream_staged_no_verify(tmp_path: Path) -> None:
    """Staged upload with verify=False skips the verify phase."""
    from icepi.flash_service import (
        CMD_INFO,
        CMD_SDRAM_WRITE_STREAM,
        CMD_SDRAM_TO_FLASH,
    )

    bitstream = tmp_path / "staged_nv.bit"
    bitstream.write_bytes(b"\xEE" * 16)

    svc = FlashService.__new__(FlashService)
    svc.port_name = "MOCK"
    svc.baud = 115200
    svc.timeout = 0.5
    svc.idle_gap = 0.002
    svc.trace = False
    svc.logger = None
    svc._erase_cmd = CMD_ERASE64
    svc._info_cache = None
    svc._sd_crc32_supported = None
    svc._sd_crc32_range_supported = None
    svc._seq = 0

    responses = [
        bytes([CMD_HELLO, MODE_SERVICE]),
        bytes([CMD_INFO, 0x7F, 0xFF, 16, 16, 16, 8, 3]),
        bytes([CMD_SDRAM_WRITE_STREAM, PING_REPLY]),
        bytes([CMD_SDRAM_TO_FLASH, PING_REPLY]),
    ]

    svc._serial = FakeSerial(responses)

    result = svc.upload_bitstream_staged(
        bitstream,
        base_address=0,
        verify=False,
    )
    assert result.bytes == 16
    assert result.padded_bytes == 16


# ---------------------------------------------------------------------------
# resolve_bitstream_target directory-is-project branch
# ---------------------------------------------------------------------------


def test_resolve_bitstream_target_directory() -> None:
    """resolve_bitstream_target on a project directory with existing bitstream."""
    thaw_dir = IMAGES_ROOT / "thaw"
    bitstream = thaw_dir / "bitstream.bit"
    if not bitstream.exists():
        pytest.skip("thaw bitstream not built")
    result = resolve_bitstream_target(str(thaw_dir))
    assert result.project == "thaw"
    assert result.bitstream == bitstream.resolve()
    assert not result.built


def test_resolve_bitstream_target_direct_file(tmp_path: Path) -> None:
    """resolve_bitstream_target on a direct .bit file path."""
    f = tmp_path / "test.bit"
    f.write_bytes(b"\xFF" * 100)
    result = resolve_bitstream_target(str(f))
    assert result.project is None
    assert result.bitstream == f.resolve()


# ---------------------------------------------------------------------------
# Item 18: SD write recovery retry logic
# ---------------------------------------------------------------------------


def test_sd_write_recovery_retries_on_timeout() -> None:
    """write_sd_block_with_recovery retries with backoff, then raises."""
    svc = MagicMock()
    svc.sd_info.return_value = MagicMock(initialized=True)
    svc.sd_write512.side_effect = FlashServiceTimeout("timeout")

    with pytest.raises(FlashServiceTimeout):
        write_sd_block_with_recovery(svc, 100, b"\x00" * 512, max_retries=1)

    # Should have been called twice (initial + 1 retry)
    assert svc.sd_write512.call_count == 2


def test_sd_write_recovery_succeeds_on_retry() -> None:
    """write_sd_block_with_recovery succeeds on second attempt."""
    svc = MagicMock()
    svc.sd_info.return_value = MagicMock(initialized=True)
    svc.sd_init.return_value = MagicMock(initialized=True)
    call_count = [0]

    def _write_side_effect(lba, data, timeout=20.0):
        call_count[0] += 1
        if call_count[0] == 1:
            raise FlashServiceTimeout("first try fails")

    svc.sd_write512.side_effect = _write_side_effect
    write_sd_block_with_recovery(svc, 100, b"\x00" * 512)
    assert call_count[0] == 2


# ---------------------------------------------------------------------------
# Item 19: stage_bundle_to_sd verification failure
# ---------------------------------------------------------------------------


def test_plan_image_roundtrip() -> None:
    """plan_image produces consistent CRC32 and SHA256."""
    import hashlib
    import binascii

    layout = load_layout()

    with tempfile.NamedTemporaryFile(suffix=".bit", delete=False) as f:
        data = b"\xDE\xAD" * 512
        f.write(data)
        tmp = f.name
    try:
        plan = plan_image(tmp, layout=layout, slot_name="boot")
        assert plan.crc32 == binascii.crc32(data) & 0xFFFFFFFF
        assert plan.sha256 == hashlib.sha256(data).hexdigest()
        assert plan.address == 0
        assert plan.bootable is True
    finally:
        os.unlink(tmp)
