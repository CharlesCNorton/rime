"""RIME control helper — thin entry point.

Command implementations live in icepi.commands.*. This module provides
the CLI parser, run_command dispatch, main entry point, and re-exports
for backwards compatibility.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from icepi.commands.helpers import (  # noqa: F401 — re-export
    CommandParseError,
    FriendlyArgumentParser,
    ShellInputError,
    build_plan_for_args,
    capture_snapshot,
    ensure_service,
    explain_device,
    explain_snapshot,
    load_layout_from_args,
    make_service,
    print_plan_header,
    print_service_mode_note,
    print_usb_notes_for_args,
    render_hexdump,
    render_sd_info_lines,
    resolved_as_dict,
    run_reload,
    snapshot_mode_label,
    validate_flash_window,
    validate_sd_window,
)
from icepi.commands.layout import cmd_layout, cmd_slot_show, cmd_slots  # noqa: F401
from icepi.commands.info import cmd_debug, cmd_doctor, cmd_info, cmd_janitor, cmd_probe, cmd_status  # noqa: F401
from icepi.commands.flash import (  # noqa: F401
    cmd_clear_error,
    cmd_flash_clear_error,
    cmd_flash_jedec,
    cmd_flash_read,
    cmd_flash_status,
    cmd_flash_verify,
)
from icepi.commands.sd import (  # noqa: F401
    cmd_sd_auto_arm,
    cmd_sd_auto_clear,
    cmd_sd_auto_info,
    cmd_sd_bundle_info,
    cmd_sd_fs_cat,
    cmd_sd_fs_info,
    cmd_sd_fs_ls,
    cmd_sd_info,
    cmd_sd_init,
    cmd_sd_install,
    cmd_sd_layout,
    cmd_sd_read,
    cmd_sd_stage_bundle,
)
from icepi.commands.install import (  # noqa: F401
    FW_FLASH_ADDR,
    FW_MAGIC,
    cmd_board_test,
    cmd_build,
    cmd_bundle,
    cmd_fw_upload,
    cmd_inspect,
    cmd_install,
    cmd_reload,
    cmd_upload,
)
from icepi.commands.shell import (  # noqa: F401
    SHELL_BANNER,
    SHELL_PROMPT,
    cmd_shell,
    run_shell_line,
    shell_help_lines,
    shell_prefix,
    split_shell_words,
    translate_shell_words,
)
from icepi.commands.errors import render_error_lines, suggest_fix  # noqa: F401
from icepi.commands.digest import cmd_digest  # noqa: F401
from icepi.commands.observe import cmd_profile, cmd_trace  # noqa: F401
from icepi.commands.swap import cmd_swap  # noqa: F401

from icepi.layout import DEFAULT_LAYOUT_FILE
from icepi.models import AUTO_CONTROL_LBA
from icepi.tools import REPO_ROOT, parse_int_value

ROOT = REPO_ROOT


def cmd_compose(args: argparse.Namespace) -> dict[str, object]:
    from icepi.compose import validate_composition, compose, write_firmware_hex, MODULES_ROOT
    from icepi.build import build_project

    plan = validate_composition(args.modules)
    print(f"Modules: {[m.name for m in plan.modules]}")
    print(f"Address map: {plan.address_map}")
    print(f"LUTs: {plan.total_luts}/{plan.available_luts} ({plan.total_luts*100//plan.available_luts}%)")
    print(f"BRAMs: {plan.total_brams}/{plan.available_brams}")
    print(f"DSPs: {plan.total_mults}/{plan.available_mults}")
    if args.validate_only:
        return {"plan": plan.address_map, "fits": plan.fits}

    firmware = [0x00000013]  # NOP placeholder
    top_sv_text = compose(plan, firmware)
    out_dir = MODULES_ROOT / "compositions"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "top.sv").write_text(top_sv_text, encoding="utf-8")
    # The generated top.sv initializes its BRAM via $readmemh("firmware.hex"),
    # so the hex must exist before synthesis or the build aborts. compose.py's
    # generate_and_build() does this; this CLI path must too.
    write_firmware_hex(firmware, out_dir / "firmware.hex")
    print(f"Generated {out_dir / 'top.sv'}")

    bitstream = build_project("compositions", clean=args.clean)
    print(f"Built {bitstream}")
    return {"plan": plan.address_map, "bitstream": str(bitstream)}



def build_parser(
    parser_cls: type[argparse.ArgumentParser] = argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    parser = parser_cls(description="Friendly RIME control helper")
    parser.add_argument("--board-config", help="path to a local board identity JSON")
    parser.add_argument("--port", help="serial port override")
    parser.add_argument("--baud", type=int, help="UART baud rate override")
    parser.add_argument("--usb-instance", help="USB instance ID override for this board")
    parser.add_argument("--usb-serial", help="USB serial override for this board")
    parser.add_argument("--usb-vid", type=parse_int_value, help="USB VID override (hex or decimal)")
    parser.add_argument("--usb-pid", type=parse_int_value, help="USB PID override (hex or decimal)")
    parser.add_argument("--layout", help="path to the flash layout JSON", default=str(DEFAULT_LAYOUT_FILE))
    parser.add_argument("--verbose", action="store_true", help="print progress updates")
    parser.add_argument("--trace", action="store_true", help="print UART frame traces")
    parser.add_argument("--traceback", action="store_true", help="print Python traceback on failure")
    parser.add_argument("--summary-json", action="store_true", help="emit a JSON summary at the end")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("layout", help="show the current flash layout and aliases")
    sub.add_parser("slots", help="show flash slots and aliases")
    p = sub.add_parser("slot-show", help="show one flash slot or alias")
    p.add_argument("slot", help="slot name or alias")
    p = sub.add_parser("info", help="show board, layout, and firmware summary")
    p.add_argument("--enter-service", action="store_true", help="enter service mode to query flash geometry and service details")
    p = sub.add_parser("status", help="show a concise board status")
    p.add_argument("--enter-service", action="store_true", help="enter service mode before reporting status")
    p = sub.add_parser("probe", help="show current app/service mode")
    p.add_argument("--enter-service", action="store_true", help="enter service mode if the app is running")
    p = sub.add_parser("doctor", help="full health report")
    p.add_argument("--no-enter-service", action="store_true", help="stay in app mode if the app is running")
    p = sub.add_parser("janitor", help="clean stale flash, SD, and error state")
    p.add_argument("--dry-run", action="store_true", help="show what would be cleaned without making changes")
    p = sub.add_parser("debug", help="dump service parser/debug state")
    p.add_argument("--enter-service", action="store_true", help="enter service mode if the app is running")
    sub.add_parser("clear-error", help="clear the sticky service error latch")
    sub.add_parser("flash-jedec", help="read the flash JEDEC identifier")
    sub.add_parser("flash-status", help="read the flash status registers")
    sub.add_parser("flash-clear-error", help="clear the sticky service error latch")
    sub.add_parser("sd-info", help="show SD card state from the resident service")
    sub.add_parser("sd-init", help="initialize the SD card in SPI mode")
    sub.add_parser("sd-layout", help="read SD block 0 and summarize the partition layout")
    p = sub.add_parser("sd-fs-info", help="inspect a FAT32 volume through board-mediated SD reads")
    p.add_argument("--partition", type=parse_int_value, help="1-based partition index override")
    p = sub.add_parser("sd-fs-ls", help="list a directory from a FAT32 volume through board-mediated SD reads")
    p.add_argument("path", nargs="?", default="/", help="directory path inside the FAT32 volume")
    p.add_argument("--partition", type=parse_int_value, help="1-based partition index override")
    p = sub.add_parser("sd-fs-cat", help="read a file from a FAT32 volume through board-mediated SD reads")
    p.add_argument("path", help="file path inside the FAT32 volume")
    p.add_argument("--partition", type=parse_int_value, help="1-based partition index override")
    p.add_argument("--output", help="write file bytes to a host file instead of printing")
    p.add_argument("--hex-width", type=int, default=16, help="hexdump bytes per row")
    p = sub.add_parser("sd-read", help="read bytes from one 512-byte SD block")
    p.add_argument("lba", type=parse_int_value, help="SD logical block address")
    p.add_argument("--offset", type=parse_int_value, default=0, help="byte offset within the block")
    p.add_argument("--length", type=parse_int_value, default=512, help="bytes to read from the block")
    p.add_argument("--output", help="write bytes to a file instead of printing a hexdump")
    p.add_argument("--hex-width", type=int, default=16, help="hexdump bytes per row")
    p = sub.add_parser("sd-bundle-info", help="read and decode a RIME bundle header from the SD card")
    p.add_argument("lba", type=parse_int_value, help="SD logical block address of the bundle header")
    p.add_argument("--manifest", action="store_true", help="read and print the embedded JSON manifest")
    p = sub.add_parser("sd-install", help="install a RIME bundle from the SD card through the resident service")
    p.add_argument("lba", type=parse_int_value, help="SD logical block address of the bundle header")
    p.add_argument("--timeout", type=float, default=120.0, help="seconds to wait for the board-side install to complete")
    p.add_argument("--reload", action="store_true", help="reload from flash after a successful install")
    p = sub.add_parser("sd-stage-bundle", help="build and stage a RIME bundle into raw SD space through the resident service")
    p.add_argument("target", help="project name, project directory, or .bit file")
    p.add_argument("--slot", help="layout slot or alias to target")
    p.add_argument("--address", type=parse_int_value, help="raw flash address override (hex or decimal)")
    p.add_argument("--reserved-bytes", type=parse_int_value, help="explicit byte budget when using a raw address override")
    p.add_argument("--build", action="store_true", help="force a rebuild when the target is a project")
    p.add_argument("--clean", action="store_true", help="clean project outputs before building")
    p.add_argument("--lba", type=parse_int_value, help="raw SD LBA override for staging")
    p.add_argument("--no-verify", action="store_true", help="skip SD readback verification after each written block")
    p = sub.add_parser("sd-auto-info", help="read and decode the adaptive SD auto-repair control block")
    p.add_argument("--lba", type=parse_int_value, default=AUTO_CONTROL_LBA, help="control block LBA (default: 1)")
    p = sub.add_parser("sd-auto-clear", help="clear the adaptive SD auto-repair control block")
    p.add_argument("--lba", type=parse_int_value, default=AUTO_CONTROL_LBA, help="control block LBA (default: 1)")
    p = sub.add_parser("sd-auto-arm", help="stage one or two bundles and arm the board-owned SD auto-repair policy")
    p.add_argument("target", help="primary project name, project directory, or .bit file")
    p.add_argument("--slot", help="layout slot or alias for the primary bundle")
    p.add_argument("--fallback-target", help="optional fallback project name, project directory, or .bit file")
    p.add_argument("--fallback-slot", help="layout slot or alias for the fallback bundle")
    p.add_argument("--build", action="store_true", help="force a rebuild when a target is a project")
    p.add_argument("--clean", action="store_true", help="clean project outputs before building")
    p.add_argument("--lba", type=parse_int_value, help="raw SD LBA override for the primary bundle")
    p.add_argument("--fallback-lba", type=parse_int_value, help="raw SD LBA override for the fallback bundle")
    p.add_argument("--attempt-limit", type=parse_int_value, default=3, help="maximum automatic repair attempts before the board disarms the control block")
    p.add_argument("--keep-armed", action="store_true", help="leave the control block armed after a successful auto-install")
    p.add_argument("--no-fallback-on-fail", action="store_true", help="do not switch to the fallback bundle after a recorded primary failure")
    p.add_argument("--no-verify", action="store_true", help="skip SD readback verification after each written block")
    p = sub.add_parser("flash-read", help="read flash bytes from a raw address")
    p.add_argument("address", type=parse_int_value, help="flash address")
    p.add_argument("length", type=parse_int_value, help="number of bytes to read")
    p.add_argument("--output", help="write bytes to a file instead of printing a hexdump")
    p.add_argument("--hex-width", type=int, default=16, help="hexdump bytes per row")
    p = sub.add_parser("upload", help="rewrite flash over the resident service")
    p.add_argument("bitstream", help="path to .bit file")
    p.add_argument("--slot", help="layout slot or alias to target")
    p.add_argument("--address", type=parse_int_value, help="raw flash address override (hex or decimal)")
    p.add_argument("--reserved-bytes", type=parse_int_value, help="explicit byte budget when using a raw address override")
    p.add_argument("--no-verify", action="store_true", help="skip readback verification")
    p.add_argument("--reload", action="store_true", help="reset from flash after upload")
    p.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompt before erasing flash")
    p = sub.add_parser("install", help="build or upload a firmware project/bitstream through the resident service")
    p.add_argument("target", help="project name, project directory, or .bit file")
    p.add_argument("--slot", help="layout slot or alias to target")
    p.add_argument("--address", type=parse_int_value, help="raw flash address override (hex or decimal)")
    p.add_argument("--reserved-bytes", type=parse_int_value, help="explicit byte budget when using a raw address override")
    p.add_argument("--build", action="store_true", help="force a rebuild when the target is a project")
    p.add_argument("--clean", action="store_true", help="clean project outputs before building")
    p.add_argument("--no-verify", action="store_true", help="skip readback verification")
    p.add_argument("--reload", action="store_true", help="reset from flash after upload")
    p.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompt before erasing flash")
    p = sub.add_parser("inspect", help="summarize a local bitstream or project output")
    p.add_argument("target", help="project name, project directory, or .bit file")
    p.add_argument("--slot", help="layout slot or alias to test-fit against")
    p.add_argument("--address", type=parse_int_value, help="raw flash address override (hex or decimal)")
    p.add_argument("--reserved-bytes", type=parse_int_value, help="explicit byte budget when using a raw address override")
    p.add_argument("--build", action="store_true", help="force a rebuild when the target is a project")
    p.add_argument("--clean", action="store_true", help="clean project outputs before building")
    p = sub.add_parser("flash-verify", help="compare flash contents against a local bitstream or project output")
    p.add_argument("target", help="project name, project directory, or .bit file")
    p.add_argument("--slot", help="layout slot or alias to verify")
    p.add_argument("--address", type=parse_int_value, help="raw flash address override (hex or decimal)")
    p.add_argument("--reserved-bytes", type=parse_int_value, help="explicit byte budget when using a raw address override")
    p.add_argument("--build", action="store_true", help="force a rebuild when the target is a project")
    p.add_argument("--clean", action="store_true", help="clean project outputs before building")
    p = sub.add_parser("bundle", help="write a versioned SD/raw-media bundle for board-side SD install")
    p.add_argument("target", help="project name, project directory, or .bit file")
    p.add_argument("--slot", help="layout slot or alias to target")
    p.add_argument("--address", type=parse_int_value, help="raw flash address override (hex or decimal)")
    p.add_argument("--reserved-bytes", type=parse_int_value, help="explicit byte budget when using a raw address override")
    p.add_argument("--build", action="store_true", help="force a rebuild when the target is a project")
    p.add_argument("--clean", action="store_true", help="clean project outputs before building")
    p.add_argument("--output", help="output path for the generated bundle")
    p = sub.add_parser("build", help="build a firmware project")
    p.add_argument("project", nargs="?", help="firmware project name")
    p.add_argument("--clean", action="store_true", help="clean build outputs first")
    p.add_argument("--top", default="top", help="top module name")
    p.add_argument("--package", default="CABGA256", help="FPGA package")
    p.add_argument("--fpga-size", default="25k", help="ECP5 size selector")
    p.add_argument("--list", action="store_true", help="list known projects and exit")
    p.add_argument("--patch", action="store_true", help="patch BRAM via ecpbram (skip synthesis)")
    p = sub.add_parser("shell", help="interactive RIME shell")
    p.add_argument("--command", dest="shell_commands", action="append", help="run one shell command and exit; may be repeated")
    p = sub.add_parser("fw-upload", help="upload compiled C firmware to flash for boot ROM loading")
    p.add_argument("firmware", help="path to firmware.bin")
    p.add_argument("--reset", action="store_true", help="trigger software reset after upload")
    p = sub.add_parser("compose", help="compose RIME-I + N modules into a single bitstream")
    p.add_argument("modules", nargs="+", help="module names to compose (e.g. anvil cairn scry)")
    p.add_argument("--clean", action="store_true", help="clean build outputs first")
    p.add_argument("--validate-only", action="store_true", help="validate resource budget without building")
    sub.add_parser("board-test", help="exercise the live board path without rewriting flash")
    sub.add_parser("reload", help="reboot the FPGA from flash")
    p = sub.add_parser("digest", help="print a machine-readable index of the repo (protocol, memory map, compositor budget, module registry) — no board needed")
    p.add_argument("module", nargs="?", help="show one module's register map instead of the whole digest")
    p.add_argument("--json", action="store_true", help="emit the full index as JSON")
    p = sub.add_parser("profile", help="profile a rime-i firmware workload on silicon via bus snoop")
    p.add_argument("--iters", type=int, help="workload loop iterations (default 4000)")
    p = sub.add_parser("trace", help="capture a rime-i bus trace on silicon and render it (+ optional VCD)")
    p.add_argument("--vcd", help="write the capture to a VCD file for waveform viewers")
    p = sub.add_parser("swap", help="compose rime-i + modules and SRAM-load it onto the board (volatile; flash untouched)")
    p.add_argument("modules", nargs="+", help="module names to compose (e.g. anvil cairn)")
    p.add_argument("--clean", action="store_true", help="clean build outputs first")
    p.add_argument("--restore", action="store_true", help="restore the flashed app over JTAG when done")
    return parser



def run_command(args: argparse.Namespace) -> int:
    handlers = {
        "layout": cmd_layout, "slots": cmd_slots, "slot-show": cmd_slot_show,
        "info": cmd_info, "status": cmd_status, "probe": cmd_probe,
        "doctor": cmd_doctor, "janitor": cmd_janitor, "debug": cmd_debug,
        "clear-error": cmd_clear_error, "flash-jedec": cmd_flash_jedec,
        "flash-status": cmd_flash_status, "flash-clear-error": cmd_flash_clear_error,
        "flash-read": cmd_flash_read,
        "sd-info": cmd_sd_info, "sd-init": cmd_sd_init, "sd-layout": cmd_sd_layout,
        "sd-fs-info": cmd_sd_fs_info, "sd-fs-ls": cmd_sd_fs_ls, "sd-fs-cat": cmd_sd_fs_cat,
        "sd-read": cmd_sd_read, "sd-bundle-info": cmd_sd_bundle_info,
        "sd-stage-bundle": cmd_sd_stage_bundle, "sd-install": cmd_sd_install,
        "sd-auto-info": cmd_sd_auto_info, "sd-auto-clear": cmd_sd_auto_clear,
        "sd-auto-arm": cmd_sd_auto_arm,
        "upload": cmd_upload, "install": cmd_install, "inspect": cmd_inspect,
        "flash-verify": cmd_flash_verify, "bundle": cmd_bundle, "build": cmd_build,
        "board-test": cmd_board_test, "shell": cmd_shell, "reload": cmd_reload,
        "fw-upload": cmd_fw_upload, "compose": cmd_compose,
        "digest": cmd_digest,
        "profile": cmd_profile, "trace": cmd_trace, "swap": cmd_swap,
    }
    result = handlers[args.command](args)
    if args.summary_json:
        print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_args = list(argv or sys.argv[1:])
    parser = build_parser(FriendlyArgumentParser)
    traceback_enabled = "--traceback" in raw_args
    try:
        args = parser.parse_args(raw_args)
        traceback_enabled = traceback_enabled or getattr(args, "traceback", False)
        return run_command(args)
    except Exception as exc:  # noqa: BLE001
        for rendered in render_error_lines(exc):
            print(rendered, file=sys.stderr)
        if traceback_enabled:
            traceback.print_exc()
        return getattr(exc, "status", 1)


if __name__ == "__main__":
    raise SystemExit(main())
