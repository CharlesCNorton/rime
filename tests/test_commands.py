"""Integration tests for command handlers using mock serial."""

from __future__ import annotations

import argparse
from unittest.mock import patch

from icepi.flash_service import (
    CMD_INFO,
    CMD_JEDEC,
    CMD_LAST_ERROR,
    CMD_SD_INFO,
    CMD_STATS,
    CMD_STATUS,
    CMD_HELLO,
    MODE_SERVICE,
)
from icepi.layout import DEFAULT_LAYOUT_FILE
from tests.test_protocol import MockSerial, _make_service


def _base_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        board_config=None,
        port="MOCK",
        baud=115200,
        usb_instance=None,
        usb_serial=None,
        usb_vid=None,
        usb_pid=None,
        layout=str(DEFAULT_LAYOUT_FILE),
        verbose=False,
        trace=False,
        traceback=False,
        summary_json=False,
        enter_service=False,
        no_enter_service=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _mock_make_service(mock: MockSerial):
    """Return a context-managed FlashService backed by the mock."""
    svc = _make_service(mock)

    class _Ctx:
        def __enter__(self):
            return svc

        def __exit__(self, *a):
            pass

    return _Ctx()


def _queue_service_probe(mock: MockSerial) -> None:
    """Queue the standard responses for a service-mode probe()."""
    mock.queue(bytes([CMD_HELLO, MODE_SERVICE]))
    mock.queue(bytes([CMD_INFO, 0x7F, 0xFF, 16, 16, 16, 8, 3]))
    mock.queue(bytes([CMD_LAST_ERROR, 0, 0, 0, 0, 0, 0]))
    mock.queue(bytes([CMD_STATS, 0, 10, 0, 0, 0, 0, 0, 0]))
    mock.queue(bytes([CMD_SD_INFO, 0x03, 0x00, 0x00, 16, 32, 0, 0, 0, 0]))


def test_cmd_layout(capsys):
    from icepi_helper import cmd_layout
    args = _base_args()
    result = cmd_layout(args)
    assert "layout" in result
    captured = capsys.readouterr()
    assert "boot" in captured.out
    assert "16777216" in captured.out


def test_cmd_slots(capsys):
    from icepi_helper import cmd_slots
    args = _base_args()
    result = cmd_slots(args)
    assert "layout" in result
    captured = capsys.readouterr()
    assert "backup" in captured.out
    assert "scratch" in captured.out


def test_cmd_slot_show(capsys):
    from icepi_helper import cmd_slot_show
    args = _base_args(slot="boot")
    result = cmd_slot_show(args)
    assert result["slot"]["name"] == "boot"
    assert result["slot"]["bootable"]


def test_cmd_flash_jedec(capsys):
    from icepi_helper import cmd_flash_jedec

    mock = MockSerial()
    # ensure_service calls probe(auto_enter=False) which does version + info + last_error + stats + sd_info
    _queue_service_probe(mock)
    # jedec command
    mock.queue(bytes([CMD_JEDEC, 0xEF, 0x40, 0x18]))
    # probe after jedec
    _queue_service_probe(mock)

    args = _base_args()
    with patch("icepi.commands.flash.make_service", return_value=_mock_make_service(mock)):
        result = cmd_flash_jedec(args)

    assert result["jedec"] == ["0xEF", "0x40", "0x18"]
    captured = capsys.readouterr()
    assert "0xEF" in captured.out


def test_cmd_flash_status(capsys):
    from icepi_helper import cmd_flash_status

    mock = MockSerial()
    _queue_service_probe(mock)
    mock.queue(bytes([CMD_STATUS, 0x00, 0x02]))
    _queue_service_probe(mock)

    args = _base_args()
    with patch("icepi.commands.flash.make_service", return_value=_mock_make_service(mock)):
        result = cmd_flash_status(args)

    assert result["status"]["sr1"] == "0x00"
    assert result["status"]["sr2"] == "0x02"


def test_cmd_build_list(capsys):
    from icepi_helper import cmd_build
    args = _base_args(list=True, project=None, clean=False, top="top",
                      package="CABGA256", fpga_size="25k")
    result = cmd_build(args)
    assert "rime" in result["projects"]


def test_cmd_upload_passes_wipe_slot_for_bootable():
    """cmd_upload must wipe the trailing space of bootable slots, same as cmd_install.

    Cure list item #6: cmd_upload was leaving stale bitstream content in
    sectors past the new image because it called upload_bitstream without
    passing wipe_slot. Admin `update` goes through this path. The board
    forensics on COM837 v5.2 showed 12 sectors of leftover bitstream from
    a previous install in the boot slot.

    This test pins the contract: when uploading to a bootable slot, the
    upload_bitstream call must receive wipe_slot=True.
    """
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch
    from icepi_helper import cmd_upload

    # Make a tiny fake bitstream file
    with tempfile.NamedTemporaryFile(suffix=".bit", delete=False) as f:
        f.write(b"\x00" * 64)
        bit_path = f.name

    try:
        args = _base_args(
            bitstream=bit_path,
            slot="boot",
            address=None,
            reserved_bytes=None,
            no_verify=True,
            reload=False,
            yes=True,
        )

        captured_calls = []

        class StubService:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def assert_service(self):
                return (5, 3)
            def info(self):
                m = MagicMock()
                m.max_program = 16
                m.erase_size = 65536
                return m
            def upload_bitstream(self, *args, **kwargs):
                captured_calls.append(kwargs)
                m = MagicMock()
                m.bytes = 64
                return m
            def probe(self, **kwargs):
                m = MagicMock()
                m.as_dict = lambda: {}
                return m

        with patch("icepi.commands.install.make_service", return_value=StubService()):
            cmd_upload(args)

        assert len(captured_calls) == 1
        assert captured_calls[0].get("wipe_slot") is True, (
            "cmd_upload must pass wipe_slot=True for bootable slots; "
            f"actual kwargs: {captured_calls[0]}"
        )
    finally:
        Path(bit_path).unlink(missing_ok=True)


def test_cmd_install_passes_wipe_slot_for_bootable():
    """Pin the same contract for cmd_install, which already does this correctly."""
    from unittest.mock import MagicMock, patch
    from icepi_helper import cmd_install
    from icepi.build import IMAGES_ROOT

    # Use the rime project so resolve_bitstream_target finds an existing bitstream
    bit_path = IMAGES_ROOT / "rime" / "bitstream.bit"
    if not bit_path.exists():
        return  # skip if no built bitstream

    args = _base_args(
        target=str(bit_path),
        slot="boot",
        address=None,
        reserved_bytes=None,
        build=False,
        clean=False,
        no_verify=True,
        reload=False,
        yes=True,
    )

    captured_calls = []

    class StubService:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def assert_service(self):
            return (5, 3)
        def info(self):
            m = MagicMock()
            m.max_program = 16
            m.erase_size = 65536
            return m
        def sdram_info(self):
            return {"init_done": False}
        def verify_bytes(self, *a, **k):
            raise RuntimeError("force fall-through to install path")
        def upload_bitstream(self, *args, **kwargs):
            captured_calls.append(("base", kwargs))
            m = MagicMock()
            m.bytes = 64
            return m
        def upload_bitstream_staged(self, *args, **kwargs):
            captured_calls.append(("staged", kwargs))
            m = MagicMock()
            m.bytes = 64
            return m
        def upload_bitstream_chunked(self, *args, **kwargs):
            captured_calls.append(("chunked", kwargs))
            m = MagicMock()
            m.bytes = 64
            return m
        def probe(self, **kwargs):
            m = MagicMock()
            m.as_dict = lambda: {}
            return m

    with patch("icepi.commands.install.make_service", return_value=StubService()):
        cmd_install(args)

    # At least one upload call must have happened with wipe_slot=True
    assert any(kwargs.get("wipe_slot") is True for _, kwargs in captured_calls), (
        f"cmd_install must pass wipe_slot=True for bootable slots; "
        f"calls: {captured_calls}"
    )
