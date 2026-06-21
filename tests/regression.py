"""RIME board regression.

Single computation that threads a CRC-32 accumulator through every board
subsystem.  Each step's output feeds the next; the final value is only
correct if every subsystem computed correctly.

    python tests/test_silicon_chain.py
    python tests/test_silicon_chain.py --verbose

Output: CHAIN:XXXXXXXX  (or CHAIN:FAIL on first error).
Each stage prints its name as it runs; --verbose adds hex detail.
"""

from __future__ import annotations

import binascii
import struct
import sys
import time as _time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

VERBOSE = "--verbose" in sys.argv
DETERMINISTIC = "--deterministic" in sys.argv  # skip timing-dependent BENCH steps
SCRATCH = 0x300000  # non-boot flash sector used for write tests


def mix(acc: int, data: bytes) -> int:
    """Fold data into the running CRC-32 accumulator."""
    return binascii.crc32(data, acc) & 0xFFFFFFFF


def step(name: str, acc: int, data: bytes) -> int:
    """Mix data into accumulator; always print stage name, verbose adds hex."""
    result = mix(acc, data)
    if VERBOSE:
        preview = data[:8].hex() + ("..." if len(data) > 8 else "")
        print(f"  {name:40s} +{len(data):5d}B  acc=0x{result:08X}  [{preview}]")
    else:
        print(f"  {name}")
    return result


def fail(reason: str) -> int:
    """Print failure and exit."""
    print(f"CHAIN:FAIL ({reason})")
    return 1


def lfsr32(seed: int) -> int:
    """32-bit LFSR for deterministic pseudorandom patterns."""
    bit = ((seed >> 0) ^ (seed >> 1) ^ (seed >> 21) ^ (seed >> 31)) & 1
    return ((seed >> 1) | (bit << 31)) & 0xFFFFFFFF


def pattern_block(base: int, n: int) -> bytes:
    """Generate n pseudorandom bytes seeded from base."""
    s = ((base + 1) * 2654435761) & 0xFFFFFFFF or 1
    out = bytearray()
    for _ in range(n):
        s = lfsr32(s)
        out.append(s & 0xFF)
    return bytes(out)


def main() -> int:
    from icepi.flash_service import (
        FlashService, FlashServiceError, FlashServiceRemoteError,
        FlashServiceProtocolError, CAPS1_SD_INFO, CAPS1_SD_WRITE512,
    )

    acc = 0x00000000

    with FlashService() as svc:
        print(f"Port: {svc.port_name}")

        # ============================================================
        # APP SHELL: exercise the full app→service→app→service cycle.
        # This proves ENTER_SERVICE, EXIT_SERVICE, command gating,
        # UPTIME continuity, and IDENTITY mode flag all work.
        # ============================================================

        major, minor = svc.version()
        if major == 4:
            # Board is in app mode — run the full round-trip
            acc = step("APP.version", acc, bytes([major, minor]))

            # PING must work in app mode
            if not svc.ping():
                return fail("app PING")

            # Service commands (INFO) must be rejected in app mode
            gate_ok = False
            try:
                svc.info()
            except (FlashServiceRemoteError, FlashServiceProtocolError):
                gate_ok = True
            except Exception:
                pass
            if not gate_ok:
                return fail("app mode did not gate service commands")
            acc = step("APP.gate", acc, b"\x01")

            # UPTIME and IDENTITY in app mode
            up1 = svc.uptime()
            acc = step("APP.uptime", acc, struct.pack(">I", up1))
            ident = svc.identity()
            if ident["name"] != "RIME" or ident["app_mode"] is not True:
                return fail("app IDENTITY")
            acc = step("APP.identity", acc, ident["name"].encode())

            # Transition to service mode
            sv = svc.enter_service_mode()
            if sv[0] != 5:
                return fail(f"ENTER_SERVICE → phase {sv[0]}")
            if not svc.ping():
                return fail("post-handoff PING")

            # UPTIME must be monotonic across the handoff
            up2 = svc.uptime()
            if up2 < up1:
                return fail(f"service UPTIME ({up2}) < app UPTIME ({up1})")

            # IDENTITY must now show app_mode=False
            if svc.identity()["app_mode"] is not False:
                return fail("service IDENTITY still shows app_mode")
            acc = step("SVC.identity", acc, bytes([0]))

            # EXIT back to app mode — proves the round-trip works
            ev = svc.exit_service_mode()
            if ev[0] != 4:
                return fail(f"EXIT_SERVICE → phase {ev[0]}")
            if not svc.ping():
                return fail("post-exit PING")
            if svc.identity()["app_mode"] is not True:
                return fail("post-exit IDENTITY")
            acc = step("EXIT.roundtrip", acc, bytes([ev[0], ev[1]]))

            # Re-enter service for the rest of the test
            sv2 = svc.enter_service_mode()
            if sv2[0] != 5:
                return fail("re-enter service")
            acc = step("REENTER", acc, bytes([sv2[0], sv2[1]]))

        elif major == 5:
            # Already in service mode (e.g. after a previous test run)
            acc = step("SVC.version", acc, bytes([major, minor]))
        else:
            return fail(f"unexpected phase {major}")

        # ============================================================
        # PROTOCOL CORE: INFO, unknown-command error handling,
        # LAST_ERROR/CLEAR_ERROR, and STATS.
        # ============================================================

        if not svc.ping():
            return fail("PING")

        # INFO must report service phase with valid geometry
        info = svc.info()
        if info.phase != 5:
            return fail(f"INFO phase {info.phase}")
        acc = step("INFO", acc, bytes([info.phase, info.version, info.caps0, info.caps1,
                                       info.max_program, info.read_chunk, info.erase_log2]))

        # Send an unknown command byte — board must respond with error frame
        got_error = False
        try:
            svc.raw_exchange(bytes([0xFE]), timeout=1.0, min_len=3)
        except (FlashServiceRemoteError, FlashServiceProtocolError):
            got_error = True
        except Exception:
            pass
        acc = step("ERROR_PATH", acc, bytes([1 if got_error else 0]))

        # Read and clear the error latch
        err = svc.last_error()
        acc = step("LAST_ERROR", acc, bytes([err.code, err.command]))
        if err.valid:
            svc.clear_last_error()
            if svc.last_error().valid:
                return fail("CLEAR_ERROR did not clear")

        # STATS command count must be non-zero (we've issued many commands)
        stats = svc.stats()
        if stats.command_count == 0:
            return fail("STATS command_count is 0")
        acc = step("STATS", acc, struct.pack(">HH", stats.command_count, stats.error_count))

        # DEBUG: the state field is packed as {3'd0, state[4:0]} in the
        # response byte.  The FSM captures state during S_DISPATCH (1)
        # because the response is built before the transition to S_TX_RESP.
        # A state value > 15 would mean the 5-bit field overflowed into
        # the padding bits — that catches a width mismatch.
        dbg = svc.debug()
        if dbg.state > 15:
            return fail(f"DEBUG state={dbg.state} exceeds 4-bit range — 5-bit packing error")
        acc = step("DEBUG.state", acc, bytes([dbg.state, dbg.current_cmd, dbg.flags]))

        # ============================================================
        # CRC.FRAME: cure list item #20. If CAPS0 bit 7 (FRAME_CRC) is set,
        # the host transparently appends a CRC-8 byte to every TX frame and
        # validates it on every RX frame. Reaching this point with PING ok
        # means CRC mode is in fact engaged. The svc._crc_mode flag was set
        # during the INFO call above; ping again to exercise the inject.
        # ============================================================
        from icepi.flash_service import CAPS0_FRAME_CRC
        if info.caps0 & CAPS0_FRAME_CRC:
            if not svc._crc_mode:
                return fail("FRAME_CRC advertised but svc._crc_mode not engaged")
            if not svc.ping():
                return fail("PING under CRC mode")
            acc = step("CRC.FRAME", acc, b"\x01")

        # ============================================================
        # FLASH: JEDEC 3x consistency, STATUS, boot-head read,
        # erase/program/verify roundtrip, stale-read regression.
        # ============================================================

        # JEDEC must return the same ID three times running
        jedec_results = [svc.jedec() for _ in range(3)]
        if not all(j == jedec_results[0] for j in jedec_results):
            return fail("JEDEC inconsistent")
        mfr, dev, cap = jedec_results[0]
        if mfr in (0x00, 0xFF):
            return fail(f"JEDEC invalid mfr=0x{mfr:02X}")
        acc = step("JEDEC.3x", acc, bytes([mfr, dev, cap]))

        # Flash STATUS: WIP bit must be clear
        sr1, sr2 = svc.status()
        if sr1 & 0x01:
            return fail("flash WIP set")
        acc = step("STATUS", acc, bytes([sr1, sr2]))

        # Read boot sector head — must not be blank
        boot_head = svc.read16(0x000000)
        if boot_head == b"\xFF" * 16:
            return fail("boot slot is blank")
        acc = step("FLASH.boot_head", acc, boot_head)

        # Cure list item #15: assert the deployed bitstream matches the in-tree
        # firmware/images/rime/bitstream.bit. The first 64 bytes always match
        # because they are the LFE5U-25F file-format header (Lattice toolchain
        # writes them identically for the same chip target). The actual
        # configuration data starts at byte 0x40, so the spot check samples a
        # chunk well past the header. If the chunks differ, the deployed
        # firmware is not the firmware in the working tree — every other test
        # below is running against a stale binary and any "PASS" is misleading.
        from pathlib import Path as _Path
        from icepi.tools import strip_bitstream_header
        local_bit = _Path(__file__).resolve().parent.parent / "firmware" / "images" / "rime" / "bitstream.bit"
        if local_bit.exists():
            local_data = strip_bitstream_header(local_bit.read_bytes())
            # Sample at offset 0x100 (256 bytes in, well past the header) and
            # offset 0x10000 (64 KiB in, deep in the configuration stream).
            # 16 bytes per probe is enough to catch any cross-version build.
            for probe_off in (0x100, 0x10000):
                if probe_off + 16 > len(local_data):
                    continue
                disk_chunk = local_data[probe_off:probe_off + 16]
                flash_chunk = svc.read16(probe_off)
                if disk_chunk != flash_chunk:
                    return fail(
                        f"BITSTREAM mismatch at flash[0x{probe_off:06X}]: "
                        f"deployed firmware != in-tree bitstream. "
                        f"flash={flash_chunk.hex()} vs disk={disk_chunk.hex()}. "
                        f"JTAG-reflash {local_bit.name} or rebuild it from current source."
                    )
            acc = step("BITSTREAM.match", acc, local_data[0x100:0x110])
        else:
            acc = step("BITSTREAM.match", acc, b"\x00")  # disk file missing — soft check

        # Write a pattern derived from current accumulator to scratch, read back
        pat = struct.pack("<I", acc) * 4
        svc.erase64(SCRATCH)
        svc.program16(SCRATCH, pat)
        rb = svc.read16(SCRATCH)
        if rb != pat:
            return fail("flash write/verify")
        acc = step("FLASH.roundtrip", acc, rb)

        # Second sequential read must not return stale data from the first
        pat2 = struct.pack("<I", acc) * 4
        svc.program16(SCRATCH + 16, pat2)
        rb1 = svc.read16(SCRATCH)
        rb2 = svc.read16(SCRATCH + 16)
        if rb1 != pat or rb2 != pat2:
            return fail("flash stale-read regression")
        acc = step("FLASH.sequential", acc, rb1 + rb2)

        # ============================================================
        # SDRAM: round-trip, row isolation, 64-chunk fill, flash
        # crosstalk, bank isolation, row boundary, address stress,
        # row errata per-bit scan.
        # ============================================================

        try:
            sdram = svc.sdram_info()
            if not sdram.init_done:
                return fail("SDRAM not initialized")
        except FlashServiceError:
            return fail("SDRAM_INFO not supported")

        # Warmup: burn the first-access init glitch
        svc.sdram_write16(0x280000, bytes(16))
        svc.sdram_read16(0x280000)

        # Single write16/read16 round-trip
        sdram_pat = struct.pack("<I", acc) * 4
        svc.sdram_write16(0x280000, sdram_pat)
        if svc.sdram_read16(0x280000) != sdram_pat:
            return fail("SDRAM round-trip")
        acc = step("SDRAM.roundtrip", acc, sdram_pat)

        # Row isolation: writing to row 1 must not clobber row 0
        row0_pat = struct.pack("<I", acc) * 4
        row1_pat = struct.pack("<I", ~acc & 0xFFFFFFFF) * 4
        svc.sdram_write16(0x280000, row0_pat)
        svc.sdram_write16(0x280200, row1_pat)
        acc = step("SDRAM.row_isolation", acc, svc.sdram_read16(0x280000))

        # 64-chunk pseudorandom fill then readback — bulk data integrity
        chunks: dict[int, bytes] = {}
        for ci in range(64):
            data = pattern_block(ci * 16, 16)
            chunks[ci] = data
            svc.sdram_write16(ci * 8, data)
        fill_acc = 0
        for ci in range(64):
            actual = svc.sdram_read16(ci * 8)
            if actual != chunks[ci]:
                return fail(f"SDRAM chunk {ci} mismatch")
            fill_acc = binascii.crc32(actual, fill_acc)
        acc = step("SDRAM.64chunk", acc, struct.pack("<I", fill_acc & 0xFFFFFFFF))

        # Flash operations must not corrupt SDRAM contents
        for _ in range(3):
            svc.erase64(SCRATCH)
            svc.program16(SCRATCH, bytes([(i * 37 + 0xA5) & 0xFF for i in range(16)]))
            svc.read16(SCRATCH)
        for ci in [0, 32, 63]:
            if svc.sdram_read16(ci * 8) != chunks[ci]:
                return fail("flash/SDRAM crosstalk")
        acc = step("SDRAM.crosstalk", acc, b"\x01")

        # Bank isolation: 4 banks must hold independent data
        banks = [(0, 0x000000), (1, 0x400000), (2, 0x800000), (3, 0xC00000)]
        for bnum, baddr in banks:
            svc.sdram_write16(baddr, bytes([bnum * 0x11 + i for i in range(16)]))
        bank_acc = 0
        for bnum, baddr in banks:
            exp = bytes([bnum * 0x11 + i for i in range(16)])
            actual = svc.sdram_read16(baddr)
            if actual != exp:
                return fail(f"bank {bnum} isolation")
            bank_acc = binascii.crc32(actual, bank_acc)
        acc = step("SDRAM.banks", acc, struct.pack("<I", bank_acc & 0xFFFFFFFF))

        # Row boundary: last word of row 0, first word of row 1
        svc.sdram_write16(0x1F8, bytes([0xAA] * 16))
        svc.sdram_write16(0x200, bytes([0xBB] * 16))
        acc = step("SDRAM.row_boundary", acc, svc.sdram_read16(0x1F8) + svc.sdram_read16(0x200))

        # Address boundary stress: columns, banks, 9-bit column addresses (A8 set)
        stress_addrs = [
            0x280000, 0x280008, 0x280010, 0x280040,  # low column offsets
            0x280080, 0x2800F8, 0x280100, 0x2801F8,   # column boundary
            0x680000, 0xA80000,                        # different banks
            0x000100, 0x0001FF, 0x000300,              # 9-bit column (A8 set, upper 256 cols)
            0x400100, 0xC001FF,                        # 9-bit column across banks
        ]
        stress_acc = 0
        for addr in stress_addrs:
            svc.sdram_write16(addr, bytes([(addr * 7 + i) & 0xFF for i in range(16)]))
        for addr in stress_addrs:
            stress_acc = binascii.crc32(svc.sdram_read16(addr), stress_acc)
        acc = step("SDRAM.addr_stress", acc, struct.pack("<I", stress_acc & 0xFFFFFFFF))

        # Row errata: test each of the 13 row address bits independently
        working_bits = 0
        for bit in range(13):
            row_addr = (1 << bit) * 0x200
            if row_addr > 0xFFFFFF:
                continue
            sentinel = bytes([0xAA] * 16)
            svc.sdram_write16(0, sentinel)
            svc.sdram_write16(row_addr, bytes([(bit + 0x10) & 0xFF] * 16))
            if svc.sdram_read16(0) == sentinel:
                working_bits += 1
        acc = step("SDRAM.row_errata", acc, bytes([working_bits]))

        # ============================================================
        # STREAM: 16-byte, 64-byte, 32K-byte, and timeout recovery.
        # The 32K test is a regression for stream_remaining[15].
        # ============================================================

        # 16-byte stream + readback
        data16 = bytes(range(16))
        svc.sdram_write_stream(0x280000, data16, timeout=5.0)
        rb16 = svc.sdram_read16(0x280000)
        if rb16 != data16:
            return fail("stream 16B")
        acc = step("STREAM.16", acc, rb16)

        # 64-byte stream: verify all 4 groups land at correct addresses
        data64 = bytes(range(64))
        svc.sdram_write_stream(0x280000, data64, timeout=5.0)
        s64_acc = 0
        for i in range(4):
            actual = svc.sdram_read16(0x280000 + i * 8)
            if actual != data64[i * 16:(i + 1) * 16]:
                return fail(f"stream 64B group {i}")
            s64_acc = binascii.crc32(actual, s64_acc)
        acc = step("STREAM.64", acc, struct.pack("<I", s64_acc & 0xFFFFFFFF))

        # 32768-byte stream: bit-15 premature-exit regression + full readback CRC.
        # The full readback was added per cure list item #14 because the original
        # spot-check of byte 0 missed an entire class of SDRAM cell-disturbance
        # bugs. With ~2000 sequential sdram_read16 calls, weak cells in unrelated
        # rows can flip bits — that's only visible by reading every byte back.
        data32k = bytes([(i * 37 + 0xA5) & 0xFF for i in range(32768)])
        svc.sdram_write_stream(0, data32k, timeout=30.0)
        if svc.sdram_read16(0) != data32k[:16]:
            return fail("stream 32K (bit-15 regression)")
        rb32k = bytearray()
        for word_offset in range(0, 16384, 8):
            rb32k.extend(svc.sdram_read16(word_offset))
        # Load per-board SDRAM errata from config/board.local.json.
        # Each entry maps a byte offset to an AND-mask for stuck cells.
        sdram_errata: dict[int, int] = {}
        try:
            import json as _json
            _board_cfg = _Path(__file__).resolve().parent.parent / "config" / "board.local.json"
            if _board_cfg.exists():
                _raw = _json.loads(_board_cfg.read_text(encoding="utf-8"))
                for _off_str, _mask in _raw.get("sdram_errata", {}).items():
                    sdram_errata[int(_off_str)] = int(_mask) & 0xFF
        except Exception:
            pass
        rb32k_masked = bytearray(rb32k)
        data32k_masked = bytearray(data32k)
        for off, mask in sdram_errata.items():
            if off < len(rb32k_masked):
                rb32k_masked[off] &= mask
                data32k_masked[off] &= mask
        if bytes(rb32k_masked) != bytes(data32k_masked):
            diffs = [(i, a, b) for i, (a, b) in enumerate(zip(rb32k_masked, data32k_masked)) if a != b]
            first_diff = diffs[0] if diffs else None
            return fail(
                f"stream 32K full-readback mismatch ({len(diffs)} bytes after errata mask); "
                f"first diff at byte {first_diff[0]}: rb=0x{first_diff[1]:02X} "
                f"exp=0x{first_diff[2]:02X}"
            )
        rb32k_crc = binascii.crc32(bytes(rb32k)) & 0xFFFFFFFF
        acc = step("STREAM.32K", acc, struct.pack("<I", rb32k_crc))

        # Timeout recovery: after a stream (success or timeout), PING must work
        try:
            svc.sdram_write_stream(0x280000, bytes(16), timeout=5.0)
        except FlashServiceError:
            pass
        if not svc.ping():
            return fail("stream timeout recovery")
        acc = step("STREAM.recovery", acc, b"\x01")

        # ============================================================
        # CHUNKED COMMIT: stream 1024 bytes to SDRAM, commit to flash,
        # host-side full verify (every 16-byte chunk), on-board verify.
        # ============================================================

        payload = bytes([(acc + i * 37) & 0xFF for i in range(1024)])
        svc.erase64(SCRATCH)
        svc.sdram_write_stream(0, payload, timeout=10.0)

        # Spot-check first and last 16 bytes in SDRAM before commit
        if svc.sdram_read16(0) != payload[:16]:
            return fail("chunked SDRAM head")
        if svc.sdram_read16((1024 - 16) // 2) != payload[-16:]:
            return fail("chunked SDRAM tail")

        # Commit from SDRAM to flash at SPI speed
        svc.sdram_to_flash(SCRATCH, 1024, timeout=30.0)

        # Host-side verify: read back every 16-byte chunk from flash
        v_acc = 0
        for ci in range(1024 // 16):
            actual = svc.read16(SCRATCH + ci * 16)
            if actual != payload[ci * 16:(ci + 1) * 16]:
                return fail(f"chunked host verify chunk {ci}")
            v_acc = binascii.crc32(actual, v_acc)
        acc = step("COMMIT.host_verify", acc, struct.pack("<I", v_acc & 0xFFFFFFFF))

        # On-board verify: re-stream payload to SDRAM, compare against flash on-board
        svc.sdram_write_stream(0, payload, timeout=10.0)
        try:
            svc.sdram_verify_flash(SCRATCH, 1024, timeout=30.0)
        except FlashServiceError:
            return fail("on-board verify")
        acc = step("COMMIT.onboard_verify", acc, b"\x01")

        # ============================================================
        # SD CARD: info, init, read MBR, write/CRC/readback roundtrip,
        # restore original block.
        # ============================================================

        has_sd = bool(info.caps1 & CAPS1_SD_INFO)
        has_sd_write = bool(info.caps1 & CAPS1_SD_WRITE512)

        if has_sd:
            try:
                sd = svc.sd_info()
                if not sd.initialized:
                    svc.sd_init()
                    sd = svc.sd_info()
                acc = step("SD.info", acc, bytes([sd.flags, sd.last_error, sd.last_r1]))

                if sd.card_present or sd.initialized:
                    # Read MBR signature region
                    sd_tail = svc.sd_read(0, offset=496, length=16)
                    acc = step("SD.mbr_tail", acc, sd_tail)

                    # Read first and last chunks of block 0
                    sd_head = svc.sd_read(0, offset=0, length=16)
                    sd_end = svc.sd_read(0, offset=496, length=16)
                    acc = step("SD.block0", acc, sd_head + sd_end)

                    if has_sd_write and sd.initialized:
                        test_lba = 7
                        # Save original block content
                        original = svc.sd_read(test_lba, offset=0, length=512)

                        # Write accumulator-derived test pattern
                        sd_pat = bytes([(acc + i * 53) & 0xFF for i in range(512)])
                        svc.sd_write512(test_lba, sd_pat)

                        # On-board CRC must match host CRC of the pattern
                        sd_crc = svc.sd_crc32(test_lba)
                        expected_crc = binascii.crc32(sd_pat) & 0xFFFFFFFF
                        if sd_crc != expected_crc:
                            svc.sd_write512(test_lba, original)
                            return fail(f"SD CRC 0x{sd_crc:08X} != 0x{expected_crc:08X}")
                        acc = step("SD.crc32", acc, struct.pack("<I", sd_crc))

                        # Readback first 16 bytes must match
                        sd_rb = svc.sd_read(test_lba, offset=0, length=16)
                        if sd_rb != sd_pat[:16]:
                            svc.sd_write512(test_lba, original)
                            return fail("SD readback mismatch")
                        acc = step("SD.roundtrip", acc, sd_rb)

                        # Restore original content and verify
                        svc.sd_write512(test_lba, original)
                        if svc.sd_read(test_lba, offset=0, length=16) != original[:16]:
                            return fail("SD restore")
                        acc = step("SD.restore", acc, original[:16])

                        # SD_INSTALL: stage a synthetic bundle to a free LBA,
                        # install it through the firmware-mediated engine, and
                        # verify the destination flash sector matches byte-exact.
                        has_sd_install = bool(info.caps1 & 0x40)  # CAPS1_SD_INSTALL
                        if has_sd_install and sd.initialized:
                            try:
                                from icepi.bundle import build_bundle_bytes
                                from icepi.layout import load_layout
                                from icepi.models import ImagePlan

                                layout = load_layout()
                                inst_pattern = bytes([(acc + i * 71) & 0xFF for i in range(512)])

                                plan = ImagePlan(
                                    bitstream_path=None,
                                    address=SCRATCH,
                                    reserved_bytes=layout.slots["scratch"].size,
                                    bitstream_bytes=len(inst_pattern),
                                    padded_bytes=512,
                                    erase_bytes=0x10000,
                                    chunk_size=16,
                                    erase_size=0x10000,
                                    block_size=layout.bundle_block_size,
                                    crc32=binascii.crc32(inst_pattern) & 0xFFFFFFFF,
                                    sha256="00" * 32,
                                    slot_name="scratch",
                                    bootable=False,
                                )
                                bundle_bytes, _ = build_bundle_bytes(
                                    plan, layout=layout, payload=inst_pattern,
                                )

                                stage_lba = 8
                                for blk_off in range(0, len(bundle_bytes), 512):
                                    chunk = bundle_bytes[blk_off:blk_off + 512].ljust(512, b"\xFF")
                                    svc.sd_write512(stage_lba + blk_off // 512, chunk)

                                svc.erase64(SCRATCH)
                                svc.sd_install(stage_lba, timeout=60.0)

                                inst_rb = svc.read(SCRATCH, len(inst_pattern))
                                if inst_rb != inst_pattern:
                                    return fail("SD_INSTALL payload mismatch")

                                inst_crc = binascii.crc32(inst_rb) & 0xFFFFFFFF
                                acc = step("SD.install", acc, struct.pack("<I", inst_crc))

                                svc.erase64(SCRATCH)
                            except (FlashServiceError, ImportError, AttributeError) as exc:
                                if VERBOSE:
                                    print(f"  SD_INSTALL: {exc}")
            except FlashServiceError as exc:
                if VERBOSE:
                    print(f"  SD: {exc}")

        # ============================================================
        # BENCH: throughput sanity for UART, flash, SDRAM, stream.
        # Times are mixed into the accumulator — they vary per run
        # but prove the subsystem responds at all.
        # ============================================================

        # In --deterministic mode (CI drift detection) skip the timing
        # benchmarks since their elapsed times vary run-to-run and would
        # cause the chain hash to drift on every run.
        if not DETERMINISTIC:
            n = 50

            # UART: 50 PINGs
            t0 = _time.perf_counter()
            for _ in range(n):
                svc.ping()
            uart_ms = (_time.perf_counter() - t0) / n * 1000
            acc = step("BENCH.uart", acc, struct.pack("<f", uart_ms))

            # Flash: 50 sequential READ16s
            t0 = _time.perf_counter()
            for i in range(n):
                svc.read16(i * 16)
            flash_ms = (_time.perf_counter() - t0) / n * 1000
            acc = step("BENCH.flash", acc, struct.pack("<f", flash_ms))

            # SDRAM: 50 write+read pairs
            t0 = _time.perf_counter()
            for _ in range(n):
                svc.sdram_write16(0x280000, bytes(range(16)))
                svc.sdram_read16(0x280000)
            sdram_ms = (_time.perf_counter() - t0) / n * 1000
            acc = step("BENCH.sdram", acc, struct.pack("<f", sdram_ms))

            # Stream: one 4096-byte bulk write
            t0 = _time.perf_counter()
            svc.sdram_write_stream(0, bytes([(i * 37) & 0xFF for i in range(4096)]), timeout=10.0)
            stream_ms = (_time.perf_counter() - t0) * 1000
            acc = step("BENCH.stream", acc, struct.pack("<f", stream_ms))

        # ============================================================
        # SDRAM RAW_WRITE ROW BOUNDARY: single-word write after row
        # change must not lose data (pre-drive OE fix).
        # ============================================================

        try:
            from icepi.flash_service import CMD_RAW_WRITE, CMD_RAW_READ
            sentinel = bytes([0xCA, 0xFE])
            # Write a single raw word at word address 0 (row 0, col 0)
            svc.raw_exchange(bytes([CMD_RAW_WRITE, 0x00, 0x00, 0x00, 0xCA, 0xFE]), timeout=2.0)
            # Write at word address 0x200 (row 1, col 0) — crosses row boundary
            svc.raw_exchange(bytes([CMD_RAW_WRITE, 0x00, 0x02, 0x00, 0xDE, 0xAD]), timeout=2.0)
            # Read back row 0, col 0
            frame0 = svc.raw_exchange(bytes([CMD_RAW_READ, 0x00, 0x00, 0x00]), timeout=2.0)
            rb0 = bytes(frame0[1:3]) if len(frame0) >= 3 else b"\x00\x00"
            # Read back row 1, col 0
            frame1 = svc.raw_exchange(bytes([CMD_RAW_READ, 0x00, 0x02, 0x00]), timeout=2.0)
            rb1 = bytes(frame1[1:3]) if len(frame1) >= 3 else b"\x00\x00"
            raw_ok = rb0 == bytes([0xCA, 0xFE]) and rb1 == bytes([0xDE, 0xAD])
            acc = step("RAW.row_boundary", acc, rb0 + rb1)
            if not raw_ok and VERBOSE:
                print(f"    RAW_WRITE row boundary: row0={rb0.hex()} row1={rb1.hex()}")
        except FlashServiceError:
            acc = step("RAW.row_boundary", acc, b"\x00")

        # ============================================================
        # SD_CRC32_RANGE: multi-block CRC must match per-block chain.
        # ============================================================

        if has_sd:
            try:
                sd = svc.sd_info()
                if sd.initialized:
                    # CRC32 of blocks 0-2 via range command
                    range_crc = svc.sd_crc32_range(0, 3)
                    # CRC32 of blocks 0-2 via individual reads
                    block_data = b""
                    for lba in range(3):
                        block_data += svc.sd_read(lba, offset=0, length=512)
                    expected_crc = binascii.crc32(block_data) & 0xFFFFFFFF
                    if range_crc != expected_crc:
                        return fail(f"SD_CRC32_RANGE 0x{range_crc:08X} != 0x{expected_crc:08X}")
                    acc = step("SD.crc32_range", acc, struct.pack("<I", range_crc))
            except FlashServiceError as exc:
                if VERBOSE:
                    print(f"  SD_CRC32_RANGE: {exc}")

        # ============================================================
        # UPLOAD_BITSTREAM: tiny synthetic image via staged path,
        # plus wipe_slot=True test (dirty a downstream sector, install
        # with max_bytes spanning 2 sectors, verify the tail is 0xFF).
        # ============================================================

        import tempfile
        from pathlib import Path as _Path
        pattern = bytes([(i * 37 + 0xC5) & 0xFF for i in range(512)])
        with tempfile.NamedTemporaryFile(suffix=".bit", delete=False) as tf:
            tf.write(pattern)
            tmp_path = _Path(tf.name)
        try:
            result = svc.upload_bitstream(
                tmp_path,
                base_address=SCRATCH,
                verify=True,
            )
            if result.bytes != len(pattern):
                return fail(f"upload_bitstream: bytes={result.bytes}")
            rb = svc.read(SCRATCH, len(pattern))
            if rb != pattern:
                return fail("upload_bitstream readback mismatch")
            acc = step("UPLOAD.bitstream", acc, struct.pack("<H", result.bytes))

            # Wipe-slot proof: dirty the downstream sector, install with
            # wipe_slot=True spanning 2 sectors, verify the dirty sector
            # is back to 0xFF.
            dirty_sector = SCRATCH + 0x10000
            svc.erase64(dirty_sector)
            dirty_pat = bytes([0xAA, 0x55] * 8)
            svc.program16(dirty_sector, dirty_pat)
            if svc.read16(dirty_sector) != dirty_pat:
                return fail("wipe_slot: dirty marker did not stick")
            svc.upload_bitstream(
                tmp_path,
                base_address=SCRATCH,
                max_bytes=0x20000,
                verify=True,
                wipe_slot=True,
            )
            tail = svc.read16(dirty_sector)
            if tail != b"\xFF" * 16:
                return fail(f"wipe_slot left dirty data: {tail.hex()}")
            acc = step("UPLOAD.wipe_slot", acc, tail)
        finally:
            tmp_path.unlink(missing_ok=True)
            svc.erase64(SCRATCH)
            try:
                svc.erase64(SCRATCH + 0x10000)
            except Exception:
                pass

        # ============================================================
        # SD ADDRESSING MODE: SD_INFO must report whether the card
        # advertises CCS (high_capacity). The firmware switches between
        # block-addressed CMD17 and byte-addressed CMD17 based on this
        # flag, and CMD16 SET_BLOCKLEN runs during init for SDSC cards.
        # We exercise sd_info() and verify the flags field is sensible
        # regardless of whether the card itself is responsive.
        # ============================================================

        try:
            sd_info_pre = svc.sd_info()
            acc = step("SD.addr_mode", acc, bytes([
                1 if sd_info_pre.high_capacity else 0,
                1 if sd_info_pre.initialized else 0,
            ]))
        except FlashServiceError:
            pass

        # ============================================================
        # v3+ FIRMWARE FEATURES: inline-key protocol and 8-byte error
        # frames. Skip cleanly against legacy v1/v2 firmware.
        # ============================================================

        if info.version >= 3:
            # Inline-key bad-key rejection
            from icepi.flash_service import CMD_ERASE64 as _CMD_E
            bad_payload = bytes([_CMD_E, 0x52, 0x49, 0x4D, 0x41, 0x30, 0x00, 0x00])  # 'RIMA'
            try:
                svc.raw_exchange(bad_payload, timeout=3.0)
                return fail("inline-key bad-key was accepted")
            except FlashServiceRemoteError as exc:
                if exc.code != 0x01:
                    return fail(f"inline-key bad-key wrong error code 0x{exc.code:02X}")
            acc = step("INLINE_KEY.bad", acc, b"\x01")

            # 8-byte error frame on unknown command
            try:
                svc.raw_exchange(bytes([0xEE]), timeout=1.0)
                return fail("0xEE was accepted")
            except FlashServiceRemoteError as exc:
                if exc.code != 0x01:
                    return fail(f"0xEE wrong code 0x{exc.code:02X}")
            except FlashServiceProtocolError as exc:
                return fail(f"0xEE returned short frame: {exc}")
            acc = step("ERROR_FRAME.8byte", acc, b"\x01")

        # ============================================================
        # ADDRESS CLAMPING: flash/SDRAM reads near the chip boundary
        # must be rejected by the host, not silently wrap.
        # ============================================================

        clamp_passed = 0
        # Valid edge reads succeed
        svc.read16(0xFFFFF0)        # last 16 bytes of flash
        svc.sdram_read16(0xFFFFF8)  # last 8 words of SDRAM
        clamp_passed += 1

        # Wrap cases must raise FlashServiceError
        wrap_cases = [
            ("read16", 0xFFFFFE, lambda: svc.read16(0xFFFFFE)),
            ("read16", 0xFFFFFF, lambda: svc.read16(0xFFFFFF)),
            ("sdram_read16", 0xFFFFFC, lambda: svc.sdram_read16(0xFFFFFC)),
            ("sdram_read16", 0xFFFFFE, lambda: svc.sdram_read16(0xFFFFFE)),
        ]
        for name, addr, fn in wrap_cases:
            try:
                fn()
                return fail(f"{name}({addr:#x}) should have been rejected")
            except FlashServiceError:
                clamp_passed += 1
        acc = step("CLAMP.boundary", acc, bytes([clamp_passed]))

        # ============================================================
        # SET_WATCHDOG: set and clear the hardware watchdog.
        # ============================================================

        wdog_ok = svc.set_watchdog(10)
        if wdog_ok:
            svc.set_watchdog(0)
        acc = step("WATCHDOG", acc, bytes([1 if wdog_ok else 0]))

        # ============================================================
        # AUTO-RECOVERY ARM: write a control block to SD LBA 1, verify
        # it round-trips correctly, then disarm. Does NOT power-cycle
        # (that requires physical intervention), but proves the control
        # block build/encode/parse path and the sd_write512/sd_read
        # round-trip at the auto-recovery LBA.
        # ============================================================

        if has_sd and has_sd_write:
            try:
                sd_r = svc.sd_info()
                if sd_r.initialized:
                    from icepi.sd import (
                        build_auto_control_block,
                        encode_auto_control_block,
                        parse_auto_control_block,
                    )

                    ctrl_lba = 1
                    original_ctrl = svc.sd_read(ctrl_lba, offset=0, length=512)

                    armed_block = build_auto_control_block(
                        primary_lba=8,
                        armed=True,
                        attempt_limit=1,
                    )
                    raw = encode_auto_control_block(armed_block)
                    svc.sd_write512(ctrl_lba, raw)

                    rb_ctrl = svc.sd_read(ctrl_lba, offset=0, length=64)
                    parsed = parse_auto_control_block(rb_ctrl)
                    if not parsed.valid:
                        svc.sd_write512(ctrl_lba, original_ctrl)
                        return fail("auto-recovery control block round-trip: invalid")
                    if not parsed.armed:
                        svc.sd_write512(ctrl_lba, original_ctrl)
                        return fail("auto-recovery control block round-trip: not armed")
                    acc = step("AUTO.arm_roundtrip", acc, bytes([1 if parsed.valid else 0, 1 if parsed.armed else 0]))

                    disarmed = build_auto_control_block(primary_lba=0, armed=False)
                    svc.sd_write512(ctrl_lba, encode_auto_control_block(disarmed))

                    svc.sd_write512(ctrl_lba, original_ctrl)
                    acc = step("AUTO.disarm", acc, b"\x01")
            except (FlashServiceError, ImportError) as exc:
                if VERBOSE:
                    print(f"  AUTO-RECOVERY: {exc}")

        # ============================================================
        # JANITOR: verify boot slot intact, clean scratch, clear errors.
        # ============================================================

        # Boot slot must not have been corrupted by any test above
        boot_verify = svc.read16(0x000000)
        if boot_verify != boot_head:
            return fail("boot slot corrupted during test")
        acc = step("JANITOR.boot_intact", acc, boot_verify)

        # Erase scratch sector and verify it's blank
        svc.erase64(SCRATCH)
        erased = svc.read16(SCRATCH)
        if erased != b"\xFF" * 16:
            return fail("scratch erase cleanup")
        acc = step("JANITOR.erase", acc, erased)

        # Clear any latched error from the test run
        err_final = svc.last_error()
        if err_final.valid:
            svc.clear_last_error()
        acc = step("JANITOR.error", acc, bytes([err_final.code]))

        # Final stats snapshot — proves the board survived the entire run
        stats_final = svc.stats()
        acc = step("FINAL.stats", acc, struct.pack(">HHHH",
                   stats_final.command_count, stats_final.erase_count,
                   stats_final.program_count, stats_final.error_count))

    print(f"CHAIN:{acc:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
