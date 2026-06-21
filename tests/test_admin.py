"""Tests for icepi_admin.py — admin wrapper command dispatch and dry-run."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

from icepi_admin import (
    build_parser,
    run_command,
    show_status,
    explain_device,
    parse_jtag_detect_output,
    quote_cmd_argument,
)


def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {
        "command": "status",
        "project": "rime",
        "dry_run": False,
        "layout": None,
        "board_config": None,
    }
    defaults.update(kwargs)
    ns = argparse.Namespace(**defaults)
    ns.layout_path = "config/icepi-layout.json"
    ns.board_config_path = None
    ns.helper_path = "icepi_helper.py"
    return ns


def test_build_parser():
    parser = build_parser()
    args = parser.parse_args(["status"])
    assert args.command == "status"
    assert args.project == "rime"
    assert args.dry_run is False


def test_build_parser_dry_run():
    parser = build_parser()
    args = parser.parse_args(["--dry-run", "flash", "thaw"])
    assert args.dry_run is True
    assert args.command == "flash"
    assert args.project == "thaw"


def test_dry_run_flash(capsys):
    args = _make_args(command="flash", project="thaw", dry_run=True)
    run_command(args)
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out
    assert "flash" in captured.out


def test_dry_run_update(capsys):
    args = _make_args(command="update", project="thaw", dry_run=True)
    run_command(args)
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out
    assert "update" in captured.out


def test_dry_run_reload(capsys):
    args = _make_args(command="reload", dry_run=True)
    run_command(args)
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out


def test_dry_run_verify(capsys):
    args = _make_args(command="verify", project="thaw", dry_run=True)
    run_command(args)
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out


def test_dry_run_flash_qspi(capsys):
    args = _make_args(command="flash-qspi", project="thaw", dry_run=True)
    run_command(args)
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out


def test_non_dry_run_status_does_not_dry_run(capsys):
    """status is not a hardware command — dry_run should not intercept it."""
    args = _make_args(command="status", dry_run=True)
    # status calls probe_target which needs a board; mock it
    mock_device = MagicMock()
    mock_device.mode = "missing"
    mock_device.com_port = None
    mock_device.driver = None
    mock_device.friendly_name = None
    mock_device.service = None
    mock_device.instance_id = None
    mock_device.notes = []
    mock_device.present = False
    with patch("icepi_admin.probe_target", return_value=mock_device):
        with patch("icepi_admin.probe_jtag_target", return_value=None):
            show_status(args)
    captured = capsys.readouterr()
    assert "[dry-run]" not in captured.out


def test_parse_jtag_detect_output_found():
    text = """
idcode 0x41111043
manufacturer Lattice
family ECP5
model LFE5U-25F
"""
    info = parse_jtag_detect_output(text)
    assert info is not None
    assert info["idcode"] == "0x41111043"
    assert info["manufacturer"] == "Lattice"
    assert info["family"] == "ECP5"
    assert info["model"] == "LFE5U-25F"


def test_parse_jtag_detect_output_empty():
    info = parse_jtag_detect_output("")
    assert info is None


def test_explain_device():
    device = MagicMock()
    device.present = True
    device.mode = "uart"
    device.com_port = "COM9"
    device.driver = "serial"
    device.friendly_name = "USB Serial Port (COM9)"
    device.service = "serial=FT231X"
    device.instance_id = "USB\\VID_0403"
    device.notes = ["UART available"]
    lines = explain_device(device)
    assert any("COM9" in line for line in lines)
    assert any("uart" in line.lower() for line in lines)


def test_quote_cmd_argument():
    assert quote_cmd_argument("simple") == "simple"
    assert quote_cmd_argument("has space") == '"has space"'
    assert quote_cmd_argument("") == '""'
