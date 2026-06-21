"""Board info, status, probe, doctor, janitor, and debug commands."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from icepi.commands.helpers import (
    capture_snapshot,
    explain_device,
    explain_snapshot,
    load_layout_from_args,
    make_service,
    print_service_mode_note,
    print_usb_notes_for_args,
    snapshot_mode_label,
)
from icepi.flash_service import (
    CAPS0_READ16,
    CAPS0_STATUS,
    CAPS0_ERASE64,
    CAPS0_PROGRAM16,
    CAPS0_LAST_ERROR,
    CAPS0_STATS,
    FlashServiceError,
    FlashServiceProtocolError,
    probe_device,
    resolve_board_target_from_args,
)

__all__ = ["cmd_info", "cmd_status", "cmd_probe", "cmd_doctor", "cmd_janitor", "cmd_debug"]


def cmd_info(args: argparse.Namespace) -> dict[str, object]:
    layout = load_layout_from_args(args)
    target = resolve_board_target_from_args(args)
    device = probe_device(target=target, baud=target.baud)
    with make_service(args) as service:
        snapshot, entered_service = capture_snapshot(service, auto_enter=args.enter_service)
    print("Board: IcePi Zero")
    print(f"Layout: {layout.path}")
    print(f"Flash size: 0x{layout.flash_size:06X} ({layout.flash_size} bytes)")
    print(f"Default slot: {layout.default_slot}")
    for line in explain_device(device):
        print(line)
    for line in explain_snapshot(snapshot):
        print(line)
    if snapshot.mode == "app" and not args.enter_service:
        print("Flash geometry is unavailable in app mode. Re-run `info --enter-service` for full service details.")
    elif snapshot.mode == "startup":
        print("Startup recovery is active. Use `status` to watch liveness or `reload` to abort and return to app mode.")
    print_service_mode_note(entered_service)
    return {
        "layout": layout.as_dict(),
        "device": asdict(device),
        "snapshot": snapshot.as_dict(),
        "entered_service": entered_service,
    }


def cmd_status(args: argparse.Namespace) -> dict[str, object]:
    target = resolve_board_target_from_args(args)
    device = probe_device(target=target, baud=target.baud)
    with make_service(args) as service:
        snapshot, entered_service = capture_snapshot(service, auto_enter=args.enter_service)
    print(f"USB mode: {device.mode}")
    if device.com_port:
        print(f"Serial port: {device.com_port}")
    print(f"Board mode: {snapshot_mode_label(snapshot)}")
    if snapshot.mode == "startup":
        print("Recovery: autonomous SD install is active.")
    elif snapshot.mode == "failsafe":
        print("Recovery: startup failsafe tripped; app mode was restored.")
    print_service_mode_note(entered_service)
    return {
        "device": asdict(device),
        "snapshot": snapshot.as_dict(),
        "entered_service": entered_service,
    }


def cmd_probe(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        snapshot, entered_service = capture_snapshot(service, auto_enter=args.enter_service)
    for line in explain_snapshot(snapshot):
        print(line)
    device = print_usb_notes_for_args(args)
    print_service_mode_note(entered_service)
    return {
        "snapshot": snapshot.as_dict(),
        "device": device,
        "entered_service": entered_service,
    }


def _doctor_line(label: str, ok: bool, detail: str = "") -> str:
    tag = "PASS" if ok else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    return f"  [{tag}] {label}{suffix}"


def cmd_doctor(args: argparse.Namespace) -> dict[str, object]:
    results: dict[str, object] = {}
    with make_service(args) as service:
        snapshot, entered_service = capture_snapshot(service, auto_enter=not args.no_enter_service)
        for line in explain_snapshot(snapshot):
            print(line)
        device = print_usb_notes_for_args(args)

        if snapshot.mode != "service":
            if snapshot.mode == "app":
                print("Doctor requires service mode. Re-run without --no-enter-service.")
            elif snapshot.mode == "startup":
                print("Startup recovery active. Use `reload` to abort first.")
            print_service_mode_note(entered_service)
            return {"snapshot": snapshot.as_dict(), "device": device, "entered_service": entered_service}

        info = service.info()
        passes = 0
        fails = 0

        def record(key: str, ok: bool, label: str, detail: str = "") -> None:
            nonlocal passes, fails
            results[key] = {"ok": ok, "detail": detail}
            print(_doctor_line(label, ok, detail))
            if ok:
                passes += 1
            else:
                fails += 1

        # --- SPI liveness probe ---
        print("\n  SPI liveness:")
        jedec_results = []
        try:
            for _ in range(3):
                jedec_results.append(service.jedec())
            mfr = jedec_results[0][0]
            jedec_ok = all(j == jedec_results[0] for j in jedec_results) and mfr not in (0x00, 0xFF)
            jedec_str = f"0x{mfr:02X} 0x{jedec_results[0][1]:02X} 0x{jedec_results[0][2]:02X}"
            if mfr == 0xEF and jedec_results[0][1] == 0x40 and jedec_results[0][2] == 0x18:
                jedec_str += " (Winbond W25Q128)"
            record("jedec_consistent", jedec_ok, "JEDEC 3x consistent", jedec_str)
        except FlashServiceError as exc:
            record("jedec_consistent", False, "JEDEC probe", str(exc))

        if info.caps0 & CAPS0_STATUS:
            try:
                sr1, sr2 = service.status()
                record("flash_wip_clear", (sr1 & 0x01) == 0, "Flash WIP clear", f"sr1=0x{sr1:02X} sr2=0x{sr2:02X}")
            except FlashServiceError as exc:
                record("flash_wip_clear", False, "Flash STATUS", str(exc))

        if info.caps0 & CAPS0_READ16:
            try:
                head = service.read16(0x000000)
                non_blank = head != b"\xFF" * 16
                record("flash_boot_present", non_blank, "Boot slot not blank", head[:8].hex(" "))
            except FlashServiceError as exc:
                record("flash_boot_present", False, "Flash READ16", str(exc))

        # --- SDRAM health probe ---
        sdram_available = False
        row_aliased = True
        try:
            sdram = service.sdram_info()
            init_done = sdram.init_done
            if init_done:
                sdram_available = True
                print("\n  SDRAM health:")
                pat_a = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE,
                               0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF])
                pat_b = bytes([0x12, 0x34, 0x56, 0x78] * 4)

                service.sdram_write16(0, pat_a)
                rb = service.sdram_read16(0)
                record("sdram_roundtrip", rb == pat_a, "Write/read roundtrip")

                service.sdram_write16(0, pat_a)
                service.sdram_write16(8, pat_b)
                col_check = service.sdram_read16(0)
                record("sdram_col_isolation", col_check == pat_a, "Column isolation")

                service.sdram_write16(0x400000, pat_b)
                bank_check = service.sdram_read16(0)
                record("sdram_bank_isolation", bank_check == pat_a, "Bank isolation")

                service.sdram_write16(0, pat_a)
                service.sdram_write16(0x200, pat_b)
                row_check = service.sdram_read16(0)
                row_aliased = row_check != pat_a
                record("sdram_row_addressing", not row_aliased,
                       "Row addressing",
                       "ALIASED (hardware defect on this board)" if row_aliased else "rows functional")

                # Staging advisory
                print("\n  SDRAM staging:")
                if row_aliased:
                    try:
                        service.sdram_write_stream(0, pat_a, timeout=5.0)
                        stream_rb = service.sdram_read16(0)
                        stream_ok = stream_rb == pat_a
                        record("sdram_chunked_staging", stream_ok, "Chunked staging (1 KiB buffer)",
                               "available" if stream_ok else "stream broken")
                    except FlashServiceError:
                        record("sdram_chunked_staging", False, "Chunked staging", "stream failed")
                else:
                    record("sdram_full_staging", True, "Full SDRAM staging", "32 MB available")
        except FlashServiceError:
            pass

        # --- Flash write-verify on scratch ---
        SCRATCH = 0x300000
        has_rw = bool(info.caps0 & CAPS0_READ16 and info.caps0 & CAPS0_ERASE64 and info.caps0 & CAPS0_PROGRAM16)
        if has_rw:
            print("\n  Flash write-verify (scratch 0x300000):")
            try:
                baseline_0 = service.read16(SCRATCH)
                baseline_1 = service.read16(SCRATCH + 16)
                test_pat = bytes([(i * 37 + 0xA5) & 0xFF for i in range(16)])
                service.erase64(SCRATCH)
                erased = service.read16(SCRATCH)
                record("scratch_erase", erased == b"\xFF" * 16, "Erase produces 0xFF")
                service.program16(SCRATCH, test_pat)
                programmed = service.read16(SCRATCH)
                record("scratch_program", programmed == test_pat, "Program + readback match")
                service.erase64(SCRATCH)
                service.program16(SCRATCH, baseline_0)
                service.program16(SCRATCH + 16, baseline_1)
                restored_0 = service.read16(SCRATCH)
                restored_1 = service.read16(SCRATCH + 16)
                record("scratch_restore", restored_0 == baseline_0 and restored_1 == baseline_1, "Baseline restored")
                err = service.last_error()
                record("scratch_no_error", not err.valid, "No error latched", "clear" if not err.valid else err.name)
            except FlashServiceError as exc:
                record("scratch_verify", False, "Flash write-verify", str(exc))

        # --- Capability matrix ---
        print("\n  Capability matrix:")
        caps_list = info.caps
        record("caps_reported", len(caps_list) > 0, "Capabilities advertised", ", ".join(caps_list))
        record("caps_geometry", info.max_program > 0 and info.read_chunk > 0,
               "Geometry valid", f"prog={info.max_program} read={info.read_chunk} erase={info.erase_size}")
        record("caps_sdram", sdram_available, "SDRAM initialized",
               "row-aliased, chunked staging" if row_aliased and sdram_available else
               "full staging" if sdram_available else "unavailable")

        if info.caps0 & CAPS0_LAST_ERROR:
            err = service.last_error()
            record("caps_error_latch", True, "Error latch readable",
                   "clear" if not err.valid else f"{err.name} on 0x{err.command:02X}")
        if info.caps0 & CAPS0_STATS:
            stats = service.stats()
            record("caps_stats", stats.command_count > 0, "Stats active", f"cmds={stats.command_count}")

        snapshot = service.probe(auto_enter=False)

    print()
    total = passes + fails
    print(f"Doctor: {passes}/{total} passed, {fails} failed")
    print_service_mode_note(entered_service)
    results["summary"] = {"passed": passes, "failed": fails, "total": total}
    results["snapshot"] = snapshot.as_dict()
    results["device"] = device
    results["entered_service"] = entered_service
    return results


def cmd_janitor(args: argparse.Namespace) -> dict[str, object]:
    """Clean up stale flash, SD, and error state without touching the boot slot."""
    from icepi.sd import (
        parse_auto_control_block,
        read_sd_bytes,
        encode_auto_control_block,
        build_auto_control_block,
    )

    layout = load_layout_from_args(args)
    results: dict[str, object] = {}
    cleaned = 0
    skipped = 0

    def _line(action: str, detail: str = "") -> None:
        suffix = f" -- {detail}" if detail else ""
        print(f"  [{action:>5s}] {suffix}" if not detail else f"  [{action:>5s}] {detail}")

    with make_service(args) as service:
        _snapshot, entered_service = capture_snapshot(service, auto_enter=True)
        if _snapshot.mode != "service":
            raise FlashServiceProtocolError("janitor requires service mode")

        info = service.info()
        print("Janitor sweep")
        print()

        # --- Clear error latch ---
        print("  Error latch:")
        err = service.last_error()
        if err.valid:
            service.clear_last_error()
            _line("CLEAN", f"cleared stale {err.name} on 0x{err.command:02X}")
            results["error_latch"] = "cleared"
            cleaned += 1
        else:
            _line("OK", "already clear")
            results["error_latch"] = "already_clear"
            skipped += 1

        # --- Verify boot slot head+tail ---
        print("\n  Boot slot integrity:")
        boot_slot = layout.resolve_slot("boot")
        head = service.read16(boot_slot.offset)
        tail = service.read16(boot_slot.offset + boot_slot.size - 16)
        head_blank = head == b"\xFF" * 16
        tail_blank = tail == b"\xFF" * 16
        if head_blank:
            _line("WARN", "boot slot head is blank -- no resident image?")
            results["boot_check"] = "blank"
            skipped += 1
        elif not head_blank and not tail_blank:
            _line("OK", f"boot slot has data (head={head[:4].hex()}, tail={tail[:4].hex()})")
            results["boot_check"] = "intact"
            skipped += 1
        else:
            _line("OK", f"boot slot partially filled (head={'data' if not head_blank else 'blank'}, tail={'data' if not tail_blank else 'blank'})")
            results["boot_check"] = "partial"
            skipped += 1

        # --- Erase non-boot slots with stale data ---
        print("\n  Non-boot flash slots:")
        slot_results = {}
        for slot_name, slot in sorted(layout.slots.items()):
            if slot.bootable:
                continue
            if not slot.writable:
                _line("SKIP", f"{slot_name}: not writable")
                slot_results[slot_name] = "not_writable"
                skipped += 1
                continue
            # Sample head and tail of the slot
            s_head = service.read16(slot.offset)
            s_tail = service.read16(slot.offset + slot.size - 16)
            if s_head == b"\xFF" * 16 and s_tail == b"\xFF" * 16:
                _line("OK", f"{slot_name}: already blank")
                slot_results[slot_name] = "already_blank"
                skipped += 1
                continue
            if args.dry_run:
                _line("WOULD", f"{slot_name}: has data, would erase {slot.size // 1024} KB")
                slot_results[slot_name] = "would_erase"
                skipped += 1
                continue
            # Erase the slot sector by sector
            sectors = slot.size // info.erase_size
            for i in range(sectors):
                addr = slot.offset + i * info.erase_size
                service.erase64(addr)
            # Verify
            v_head = service.read16(slot.offset)
            v_tail = service.read16(slot.offset + slot.size - 16)
            if v_head == b"\xFF" * 16 and v_tail == b"\xFF" * 16:
                _line("CLEAN", f"{slot_name}: erased {sectors} sectors ({slot.size // 1024} KB)")
                slot_results[slot_name] = "erased"
                cleaned += 1
            else:
                _line("FAIL", f"{slot_name}: erase did not produce 0xFF")
                slot_results[slot_name] = "erase_failed"
                skipped += 1
        results["slots"] = slot_results

        # --- Clear stale SD auto-recovery control block ---
        print("\n  SD auto-recovery control block:")
        try:
            sd_info = service.sd_info()
            if not sd_info.initialized:
                service.sd_init()
            ctrl_data = read_sd_bytes(service, lba=1, length=512)
            ctrl = parse_auto_control_block(ctrl_data, lba=1)
            if ctrl.valid_magic and not ctrl.armed:
                already_clean = (ctrl.attempt_limit == 0 and ctrl.attempt_count == 0
                                 and ctrl.last_result == 0 and ctrl.last_error_code == 0
                                 and ctrl.primary_lba == 0 and ctrl.fallback_lba == 0)
                if already_clean:
                    _line("OK", "control block present but already clean (disarmed, no history)")
                    results["sd_auto"] = "already_clean"
                    skipped += 1
                elif args.dry_run:
                    _line("WOULD", f"stale control block (result={ctrl.last_result_name}), would clear")
                    results["sd_auto"] = "would_clear"
                    skipped += 1
                else:
                    blank = build_auto_control_block(armed=False, attempt_limit=0)
                    service.sd_write512(1, encode_auto_control_block(blank))
                    _line("CLEAN", f"cleared stale control block (was {ctrl.last_result_name})")
                    results["sd_auto"] = "cleared"
                    cleaned += 1
            elif ctrl.valid_magic and ctrl.armed:
                _line("SKIP", "control block is armed -- not touching it")
                results["sd_auto"] = "armed_skip"
                skipped += 1
            elif not ctrl.valid_magic:
                _line("OK", "no control block present")
                results["sd_auto"] = "absent"
                skipped += 1
        except FlashServiceError as exc:
            _line("SKIP", f"SD not available ({exc})")
            results["sd_auto"] = "sd_unavailable"
            skipped += 1

        snapshot = service.probe(auto_enter=False)

    print()
    print(f"Janitor: {cleaned} cleaned, {skipped} ok/skipped")
    if args.dry_run:
        print("(dry run -- no changes were made)")
    print_service_mode_note(entered_service)
    results["summary"] = {"cleaned": cleaned, "skipped": skipped}
    results["snapshot"] = snapshot.as_dict()
    results["entered_service"] = entered_service
    return results


def cmd_debug(args: argparse.Namespace) -> dict[str, object]:
    with make_service(args) as service:
        snapshot, entered_service = capture_snapshot(service, auto_enter=args.enter_service)
        if snapshot.mode != "service":
            raise FlashServiceProtocolError("debug requires service mode")
        debug = service.debug()
    print(f"State: {debug.state_name} ({debug.state})")
    print(f"Current command: {debug.current_cmd_name} (0x{debug.current_cmd:02X})")
    print(f"SPI op: {debug.spi_op_name} ({debug.spi_op})")
    print(f"Address index: {debug.addr_index}")
    print(f"Data index: {debug.data_index}")
    print(f"Response cursor: {debug.resp_pos}/{debug.resp_len}")
    print(f"Flags: {', '.join(debug.flag_names)}")
    print(f"Auto state: {debug.auto_state_name} ({debug.auto_state})")
    print(f"Auto exit: {debug.auto_exit_reason_name} (0x{debug.auto_exit_reason:02X})")
    print(f"Auto exit detail: 0x{debug.auto_exit_detail:02X}")
    print(f"Auto init attempts: {debug.auto_init_attempts}")
    print(f"Auto progress: {debug.auto_progress_text}")
    print(
        "Auto staged result: "
        f"{debug.auto_write_result_name} ({debug.auto_write_result})"
    )
    print(f"Auto staged source LBA: {debug.auto_write_source_lba}")
    print_service_mode_note(entered_service)
    return {
        "snapshot": snapshot.as_dict(),
        "debug": asdict(debug),
        "entered_service": entered_service,
    }
