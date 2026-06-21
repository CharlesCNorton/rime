"""Install, upload, inspect, bundle, build, reload, board-test, fw-upload commands."""

from __future__ import annotations
from typing import Any

import argparse
import binascii
import struct
from dataclasses import asdict
from pathlib import Path

from icepi.commands.helpers import (
    build_plan_for_args,
    capture_snapshot,
    explain_device,
    make_service,
    print_plan_header,
    print_service_mode_note,
    resolved_as_dict,
    run_reload,
)
from icepi.build import FIRMWARE_ROOT, available_projects, resolve_bitstream_target, run_build
from icepi.bundle import write_bundle
from icepi.flash_service import (
    CAPS0_LAST_ERROR,
    CAPS0_READ16,
    CAPS0_STATS,
    CAPS0_STATUS,
    CAPS1_DEBUG,
    CAPS1_SD_INFO,
    CAPS1_SD_READ16,
    CAPS1_SD_WRITE512,
    FlashServiceError,
    FlashServiceProtocolError,
    probe_device,
    resolve_board_target_from_args,
)
from icepi.layout import render_plan_lines
from icepi.sd import read_sd_bytes
from icepi.tools import make_progress_renderer, strip_bitstream_header

import time as _time


def _try_recover_service(service: Any) -> None:
    """Attempt to recover the service after a failed SDRAM stream.

    The FSM may be stuck in S_SDRAM_STREAM waiting for bytes.  Strategy:
    1. Flush padding bytes to satisfy any remaining stream count.
    2. Close and reopen the serial handle to reset OS buffers.
    3. Wait for the board to settle.
    4. Re-assert service mode.
    """
    try:
        service.flush_raw(b"\xFF" * 4096)
        _time.sleep(0.5)
    except Exception:
        pass
    service.close()
    _time.sleep(0.5)
    service.open()
    _time.sleep(0.2)
    try:
        service.assert_service()
    except FlashServiceError as inner:
        raise FlashServiceError(
            "Board did not recover after SDRAM stream failure. "
            "Use `reload` to restore the service, then retry."
        ) from inner


__all__ = [
    "cmd_upload",
    "cmd_install",
    "cmd_inspect",
    "cmd_bundle",
    "cmd_build",
    "cmd_board_test",
    "cmd_reload",
    "cmd_fw_upload",
    "FW_FLASH_ADDR",
    "FW_MAGIC",
]

FW_FLASH_ADDR = 0x300000
FW_MAGIC = 0x524D4657


def cmd_upload(args: argparse.Namespace) -> dict[str, object]:
    bitstream = Path(args.bitstream).resolve()
    if not bitstream.exists():
        raise FileNotFoundError(bitstream)
    renderer = make_progress_renderer(args.verbose)
    with make_service(args) as service:
        service.assert_service()
        info = service.info()
        layout, plan = build_plan_for_args(bitstream, args, chunk_size=info.max_program, erase_size=info.erase_size)
        for line in render_plan_lines(plan):
            print(line)
        print(f"Layout default slot: {layout.default_slot}")
        if args.reload and not plan.bootable:
            raise FlashServiceError("reload is only allowed for a bootable slot; generate a bundle or upload without --reload")
        # Bootable slots get a full-slot wipe so old-bitstream remnants past the new
        # image's padded end never survive a fresh upload. Same policy as cmd_install.
        wipe = bool(plan.bootable)
        result = service.upload_bitstream(bitstream, base_address=plan.address, max_bytes=plan.reserved_bytes, verify=not args.no_verify, progress=renderer, wipe_slot=wipe)
        snapshot = service.probe(auto_enter=False)
    print(f"Uploaded {result.bytes} bytes from {bitstream}")
    if args.reload:
        print("Reloading from flash.")
        run_reload()
    else:
        print("Note: board remains in service mode until `reload` restores the resident app.")
    return {"upload": result, "snapshot": snapshot.as_dict(), "plan": plan.as_dict(), "bitstream": str(bitstream)}


def cmd_install(args: argparse.Namespace) -> dict[str, object]:
    resolved = resolve_bitstream_target(args.target, build_if_project=args.build or Path(args.target).expanduser().is_dir() or (FIRMWARE_ROOT / args.target).is_dir(), clean=args.clean)
    renderer = make_progress_renderer(args.verbose)
    with make_service(args) as service:
        service.assert_service()
        info = service.info()
        layout, plan = build_plan_for_args(resolved.bitstream, args, chunk_size=info.max_program, erase_size=info.erase_size)
        print_plan_header(resolved)
        for line in render_plan_lines(plan):
            print(line)
        print(f"Layout default slot: {layout.default_slot}")
        if args.reload and not plan.bootable:
            raise FlashServiceError("reload is only allowed for a bootable slot; choose a bootable slot or install without --reload")
        if not getattr(args, "yes", False):
            try:
                answer = input(f"Erase and program {plan.erase_bytes} bytes at 0x{plan.address:06X}? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return {"aborted": True}
        already_installed = False
        if not args.no_verify:
            try:
                bitstream_data = strip_bitstream_header(resolved.bitstream.read_bytes())
                service.verify_bytes(plan.address, bitstream_data[:min(len(bitstream_data), 48)])
                service.verify_bytes(plan.address + len(bitstream_data) - 16, bitstream_data[-16:])
                already_installed = True
            except Exception:
                pass
        if already_installed:
            print("Flash already matches bitstream; skipping write.")
            snapshot = service.probe(auto_enter=False)
            if args.reload:
                print("Reloading from flash.")
                run_reload()
            return {"resolved": resolved_as_dict(resolved), "already_installed": True, "snapshot": snapshot.as_dict(), "plan": plan.as_dict()}
        sdram_path = "direct"
        try:
            sdram = service.sdram_info()
            if sdram.init_done:
                pat_a = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE,
                               0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF])
                pat_b = bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0,
                               0xFE, 0xDC, 0xBA, 0x98, 0x76, 0x54, 0x32, 0x10])
                service.sdram_write16(0x280000, pat_a)
                service.sdram_write16(0x280200, pat_b)
                readback_a = service.sdram_read16(0x280000)
                if readback_a != pat_a:
                    try:
                        service.sdram_write_stream(0, pat_a, timeout=5.0)
                        readback = service.sdram_read16(0)
                        if readback == pat_a:
                            sdram_path = "chunked"
                        else:
                            print("SDRAM stream readback mismatch; using direct upload path.")
                    except FlashServiceError as exc:
                        print(f"SDRAM stream probe failed ({exc}); using direct upload path.")
                else:
                    try:
                        service.sdram_write_stream(0x280000, pat_a, timeout=5.0)
                        readback = service.sdram_read16(0x280000)
                        if readback == pat_a:
                            sdram_path = "staged"
                        else:
                            print("SDRAM stream readback mismatch; using direct upload path.")
                    except FlashServiceError as exc:
                        print(f"SDRAM stream probe failed ({exc}); using direct upload path.")
        except Exception:
            pass
        # Bootable slots get a full-slot wipe so old-bitstream remnants past
        # the new image's padded end never survive a fresh install.
        wipe = bool(plan.bootable)
        result = None
        if sdram_path == "staged":
            try:
                result = service.upload_bitstream_staged(resolved.bitstream, base_address=plan.address, max_bytes=plan.reserved_bytes, verify=not args.no_verify, progress=renderer, wipe_slot=wipe)
            except FlashServiceError as exc:
                print(f"Staged upload failed: {exc}")
                print("Falling back to chunked SDRAM path.")
                _try_recover_service(service)
                service.unlock()
        elif sdram_path == "chunked":
            try:
                result = service.upload_bitstream_chunked(resolved.bitstream, base_address=plan.address, max_bytes=plan.reserved_bytes, verify=not args.no_verify, progress=renderer, wipe_slot=wipe)
            except FlashServiceError as exc:
                print(f"Chunked upload failed: {exc}")
                _try_recover_service(service)
                service.unlock()
        if result is None:
            result = service.upload_bitstream(resolved.bitstream, base_address=plan.address, max_bytes=plan.reserved_bytes, verify=not args.no_verify, progress=renderer, wipe_slot=wipe)
        snapshot = service.probe(auto_enter=False)
    print(f"Installed {result.bytes} bytes from {resolved.label}")
    if args.reload:
        print("Reloading from flash.")
        run_reload()
    else:
        print("Note: board remains in service mode until `reload` restores the resident app.")
    return {"resolved": resolved_as_dict(resolved), "upload": result, "snapshot": snapshot.as_dict(), "plan": plan.as_dict()}


def cmd_inspect(args: argparse.Namespace) -> dict[str, object]:
    resolved = resolve_bitstream_target(args.target, build_if_project=args.build, clean=args.clean)
    _layout, plan = build_plan_for_args(resolved.bitstream, args, chunk_size=16, erase_size=65536)
    print_plan_header(resolved)
    for line in render_plan_lines(plan):
        print(line)
    return {"resolved": resolved_as_dict(resolved), "plan": plan.as_dict(), "bitstream": str(resolved.bitstream)}


def cmd_bundle(args: argparse.Namespace) -> dict[str, object]:
    resolved = resolve_bitstream_target(args.target, build_if_project=args.build, clean=args.clean)
    layout, plan = build_plan_for_args(resolved.bitstream, args, chunk_size=16, erase_size=65536)
    output = Path(args.output).resolve() if args.output else resolved.bitstream.with_suffix(".icepi.bundle.bin")
    bundle_path, manifest = write_bundle(output, plan=plan, layout=layout)
    print_plan_header(resolved)
    for line in render_plan_lines(plan):
        print(line)
    print(f"Bundle: {bundle_path}")
    return {"resolved": resolved_as_dict(resolved), "bundle": str(bundle_path), "manifest": manifest, "plan": plan.as_dict()}


def cmd_build(args: argparse.Namespace) -> dict[str, object]:
    if args.list:
        for project in available_projects():
            print(project)
        return {"projects": available_projects()}
    if not args.project:
        raise ValueError("build requires a project name unless --list is used")
    if getattr(args, "patch", False):
        from icepi.build import patch_bram
        bitstream = patch_bram(args.project)
        print(f"Patched {bitstream}")
        return {"project": args.project, "bitstream": str(bitstream), "patched": True}
    bitstream = run_build(args.project, clean=args.clean, top=args.top, package=args.package, fpga_size=args.fpga_size)
    print(f"Built {bitstream}")
    return {"project": args.project, "bitstream": str(bitstream)}


def _test_line(label: str, ok: bool, detail: str = "") -> str:
    tag = "PASS" if ok else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    return f"  [{tag}] {label}{suffix}"


def cmd_board_test(args: argparse.Namespace) -> dict[str, object]:
    target = resolve_board_target_from_args(args)
    device = probe_device(target=target, baud=target.baud)
    results: dict[str, object] = {}
    passes = 0
    fails = 0

    def record(key: str, ok: bool, label: str, detail: str = "") -> None:
        nonlocal passes, fails
        results[key] = {"ok": ok, "detail": detail}
        print(_test_line(label, ok, detail))
        if ok:
            passes += 1
        else:
            fails += 1

    with make_service(args) as service:
        snapshot, entered_service = capture_snapshot(service, auto_enter=True)
        if snapshot.mode != "service":
            raise FlashServiceProtocolError("board-test requires service mode")

        ping_ok = service.ping()
        record("ping", ping_ok, "PING acknowledged")

        info = service.info()
        caps_list = info.caps
        record("info_caps", len(caps_list) > 0, "INFO reports capabilities", ", ".join(caps_list))

        try:
            mfr, dev, cap = service.jedec()
            jedec_ok = mfr != 0x00 and mfr != 0xFF
            record("jedec", jedec_ok, "JEDEC flash identity",
                   f"0x{mfr:02X} 0x{dev:02X} 0x{cap:02X}" + (" (Winbond W25Q128)" if mfr == 0xEF and dev == 0x40 and cap == 0x18 else ""))
        except FlashServiceError as exc:
            record("jedec", False, "JEDEC flash identity", str(exc))

        if info.caps0 & CAPS0_STATUS:
            try:
                sr1, sr2 = service.status()
                wip_clear = (sr1 & 0x01) == 0
                record("flash_status", wip_clear, "Flash STATUS WIP clear", f"sr1=0x{sr1:02X} sr2=0x{sr2:02X}")
            except FlashServiceError as exc:
                record("flash_status", False, "Flash STATUS", str(exc))

        if info.caps0 & CAPS0_READ16:
            try:
                head = service.read16(0x000000)
                non_blank = head != b"\xFF" * 16
                record("flash_read", len(head) == 16, "Flash READ16 returns 16 bytes", f"{len(head)} bytes")
                record("flash_content", non_blank, "Flash boot slot is not blank", head[:8].hex(" "))
            except FlashServiceError as exc:
                record("flash_read", False, "Flash READ16", str(exc))

        if info.caps0 & CAPS0_LAST_ERROR:
            try:
                err = service.last_error()
                record("last_error", True, "LAST_ERROR readable",
                       "clear" if not err.valid else f"{err.name} on 0x{err.command:02X}")
            except FlashServiceError as exc:
                record("last_error", False, "LAST_ERROR", str(exc))

        if info.caps0 & CAPS0_STATS:
            try:
                stats = service.stats()
                record("stats", stats.command_count > 0, "STATS command count > 0", f"cmds={stats.command_count}")
            except FlashServiceError as exc:
                record("stats", False, "STATS", str(exc))

        if info.caps1 & CAPS1_DEBUG:
            try:
                dbg = service.debug()
                record("debug", True, "DEBUG state readable",
                       f"state={dbg.state_name} flags={','.join(dbg.flag_names)}")
            except FlashServiceError as exc:
                record("debug", False, "DEBUG state", str(exc))

        sdram_tested = False
        try:
            sdram = service.sdram_info()
            init_done = sdram.init_done
            record("sdram_info", True, "SDRAM_INFO readable", f"init_done={init_done}")
            if init_done:
                test_addr = 0x280000
                test_pattern = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE,
                                      0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF])
                try:
                    service.sdram_write16(test_addr, test_pattern)
                    readback = service.sdram_read16(test_addr)
                    match = readback == test_pattern
                    record("sdram_roundtrip", match, "SDRAM write-readback roundtrip",
                           f"match={match}" + ("" if match else f" got={readback.hex(' ')}"))
                    sdram_tested = True
                except FlashServiceError as exc:
                    record("sdram_roundtrip", False, "SDRAM write-readback", str(exc))
        except FlashServiceError:
            record("sdram_info", False, "SDRAM_INFO", "not supported or failed")

        has_sd_info = bool(info.caps1 & CAPS1_SD_INFO)
        has_sd_read = bool(info.caps1 & CAPS1_SD_READ16)
        has_sd_write = bool(info.caps1 & CAPS1_SD_WRITE512)

        if has_sd_info:
            try:
                sd = service.sd_info()
                record("sd_info", True, "SD_INFO readable",
                       f"present={sd.card_present} init={sd.initialized} hc={sd.high_capacity}")
                if has_sd_read and sd.initialized:
                    try:
                        sd_tail = service.sd_read(0, offset=496, length=16)
                        record("sd_read", len(sd_tail) == 16, "SD read LBA0 tail", sd_tail.hex(" "))
                    except FlashServiceError as exc:
                        record("sd_read", False, "SD read", str(exc))
                    if has_sd_write:
                        test_lba = 7
                        try:
                            original = read_sd_bytes(service, lba=test_lba, length=512)
                            pattern = bytes([(i * 37 + 0xA5) & 0xFF for i in range(512)])
                            service.sd_write512(test_lba, pattern)
                            rb = read_sd_bytes(service, lba=test_lba, length=512)
                            sd_ok = rb == pattern
                            service.sd_write512(test_lba, original)
                            record("sd_roundtrip", sd_ok, "SD write-readback roundtrip",
                                   "match" if sd_ok else "MISMATCH")
                        except FlashServiceError as exc:
                            record("sd_roundtrip", False, "SD write-readback", str(exc))
                            try:
                                service.sd_write512(test_lba, original)
                            except Exception:
                                pass
                elif has_sd_read and not sd.initialized:
                    print("  [SKIP] SD read/write -- card not initialized")
                elif not has_sd_read:
                    print("  [SKIP] SD read -- SD_READ16 not advertised")
            except FlashServiceError as exc:
                record("sd_info", False, "SD_INFO", str(exc))
        else:
            print("  [----] SD: not supported by this service image")

        snapshot = service.probe(auto_enter=False)

    print()
    for line in explain_device(device):
        print(line)
    print()
    total = passes + fails
    print(f"Board test: {passes}/{total} passed, {fails} failed")
    if sdram_tested:
        sdram_rt = results.get("sdram_roundtrip")
        sdram_ok = isinstance(sdram_rt, dict) and bool(sdram_rt.get("ok"))
        results["sdram_staging"] = "ok" if sdram_ok else "unreliable"
    results["sd_supported"] = has_sd_info
    results["device"] = asdict(device)
    results["snapshot"] = snapshot.as_dict()
    results["entered_service"] = entered_service
    results["summary"] = {"passed": passes, "failed": fails, "total": total}
    print_service_mode_note(entered_service)
    return results


def cmd_reload(_args: argparse.Namespace) -> dict[str, object]:
    reloaded = run_reload()
    if reloaded:
        print("Reload command completed.")
    return {"reloaded": reloaded}


def cmd_fw_upload(args: argparse.Namespace) -> dict[str, object]:
    fw_path = Path(args.firmware)
    if not fw_path.exists():
        raise FileNotFoundError(f"{fw_path} not found")
    fw_data = fw_path.read_bytes()
    if len(fw_data) > 16384:
        raise ValueError(f"firmware too large ({len(fw_data)} bytes, max 16384)")
    fw_crc = binascii.crc32(fw_data) & 0xFFFFFFFF
    header = struct.pack(">III", FW_MAGIC, len(fw_data), fw_crc) + b"\x00" * 4
    payload = header + fw_data
    if len(payload) % 16 != 0:
        payload += b"\x00" * (16 - len(payload) % 16)
    verbose = getattr(args, "verbose", False)
    with make_service(args) as svc:
        svc.assert_service()
        erase_end = FW_FLASH_ADDR + len(payload)
        addr = FW_FLASH_ADDR
        while addr < erase_end:
            if verbose:
                print(f"  erase 0x{addr:06X}")
            svc.erase64(addr)
            addr += 65536
        for offset in range(0, len(payload), 16):
            chunk = payload[offset: offset + 16]
            svc.program16(FW_FLASH_ADDR + offset, chunk)
            if verbose and offset % 256 == 0:
                print(f"  program 0x{FW_FLASH_ADDR + offset:06X}")
        hdr_rb = svc.read16(FW_FLASH_ADDR)
        if hdr_rb[:4] != header[:4]:
            raise FlashServiceError("firmware header readback mismatch")
    print(f"Firmware uploaded: {len(fw_data)} bytes at 0x{FW_FLASH_ADDR:06X}")
    print("Trigger a software reset or power cycle to load via boot ROM.")
    if getattr(args, "reset", False):
        with make_service(args) as svc:
            svc.software_reset()
        print("Software reset triggered.")
    return {"uploaded": len(fw_data)}
