#!/usr/bin/env python3
"""Coprocessor parallel regression: 3-way segmented CRC-32.

Required silicon regression for any change to rime_i_core.sv, rime_ii_core.sv,
coproc.sv, compose.py, or the compositor bus protocol.

Run:
    python tests/test_coproc_regression.py

Exit 0 on success, 1 on failure.
"""
from __future__ import annotations

import binascii
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo))
sys.path.insert(0, str(_repo / "modules"))
sys.path.insert(0, str(_repo / "modules" / "rime-i"))

from gen_firmware import RV32I  # noqa: E402
from icepi.build import build_project  # noqa: E402
from icepi.compose import validate_composition, compose, write_firmware_hex, MODULES_ROOT  # noqa: E402

x0, ra, sp = 0, 1, 2
t0, t1, t2, t3 = 5, 6, 7, 28
a0, a1 = 10, 11
s0, s1, s2, s3, s4, s5, s6, s7 = 8, 9, 18, 19, 20, 21, 22, 23
UART = 0x20000000

DATA = bytes([(i * 131 + i // 256 * 47 + 0xA5) & 0xFF for i in range(768)])
SEGMENT_SIZE = 256
N_SEGMENTS = 3

EXPECTED_CRCS = []
for _i in range(N_SEGMENTS):
    _seg = DATA[_i * SEGMENT_SIZE:(_i + 1) * SEGMENT_SIZE]
    EXPECTED_CRCS.append(binascii.crc32(_seg) & 0xFFFFFFFF)

assert len(set(EXPECTED_CRCS)) == N_SEGMENTS


def make_crc_firmware():
    a = RV32I()
    DATA_ADDR = 0x100
    N_BYTES = 256
    POLY = 0xEDB88320
    a.li(a0, 0xFFFFFFFF)
    a.li(s1, DATA_ADDR)
    a.li(s2, DATA_ADDR + N_BYTES)
    a.li(s3, POLY & 0xFFFFFFFF)
    a.label("byte_loop")
    a.bge(s1, s2, "crc_done")
    a.lb(t0, s1, 0)
    a.andi(t0, t0, 0xFF)
    a.xor(a0, a0, t0)
    a.addi(t1, x0, 8)
    a.label("bit_loop")
    a.beq(t1, x0, "bit_done")
    a.andi(t0, a0, 1)
    a.srli(a0, a0, 1)
    a.beq(t0, x0, "no_xor")
    a.xor(a0, a0, s3)
    a.label("no_xor")
    a.addi(t1, t1, -1)
    a.j("bit_loop")
    a.label("bit_done")
    a.addi(s1, s1, 1)
    a.j("byte_loop")
    a.label("crc_done")
    a.xori(a0, a0, -1)
    a.lui(s0, UART >> 12)
    a.sw(a0, s0, 0)
    a.lui(t0, 0xDEAD0)
    a.sw(t0, s0, 0)
    a.label("spin")
    a.j("spin")
    a.resolve()
    return a.code


def build_primary_firmware(crc_fw):
    CP_BASES = [0x30000000, 0x31000000, 0x32000000]
    DATA_REG_OFFSET = 0x020 + 64 * 4

    a = RV32I()
    a.lui(sp, 0x00001)
    a.lui(s5, UART >> 12)
    a.j("main")

    # putc
    a.label("putc")
    a.lw(t0, s5, 4)
    a.bne(t0, x0, "putc")
    a.sw(a0, s5, 0)
    a.ret()

    # puthex
    a.label("puthex")
    a.addi(sp, sp, -8)
    a.sw(ra, sp, 4)
    a.sw(s0, sp, 0)
    a.mv(s0, a0)
    a.addi(s1, x0, 28)
    a.label("ph_l")
    a.blt(s1, x0, "ph_x")
    a.srl(a0, s0, s1)
    a.andi(a0, a0, 0xF)
    a.addi(t0, x0, 10)
    a.blt(a0, t0, "ph_d")
    a.addi(a0, a0, 55)
    a.j("ph_e")
    a.label("ph_d")
    a.addi(a0, a0, 48)
    a.label("ph_e")
    a.call("putc")
    a.addi(s1, s1, -4)
    a.j("ph_l")
    a.label("ph_x")
    a.lw(s0, sp, 0)
    a.lw(ra, sp, 4)
    a.addi(sp, sp, 8)
    a.ret()

    a.label("main")

    for i in range(N_SEGMENTS):
        a.lui(s6, CP_BASES[i] >> 12)
        a.addi(t0, x0, 4)
        a.sw(t0, s6, 0)
        for j, word in enumerate(crc_fw):
            a.li(t0, word)
            a.sw(t0, s6, 0x020 + j * 4)
        seg = DATA[i * SEGMENT_SIZE:(i + 1) * SEGMENT_SIZE]
        for j in range(0, SEGMENT_SIZE, 4):
            word = seg[j] | (seg[j + 1] << 8) | (seg[j + 2] << 16) | (seg[j + 3] << 24)
            a.li(t0, word & 0xFFFFFFFF)
            a.sw(t0, s6, DATA_REG_OFFSET + j)

    for i in range(N_SEGMENTS):
        a.lui(s6, CP_BASES[i] >> 12)
        a.addi(t0, x0, 1)
        a.sw(t0, s6, 0)

    a.addi(s7, x0, 0)
    a.label("poll")
    a.addi(s7, s7, 1)
    for i in range(N_SEGMENTS):
        a.lui(s6, CP_BASES[i] >> 12)
        a.lw(t0, s6, 4)
        a.andi(t0, t0, 2)
        a.beq(t0, x0, "poll")

    for i in range(N_SEGMENTS):
        a.lui(s6, CP_BASES[i] >> 12)
        for ch in f"C{i}:":
            a.addi(a0, x0, ord(ch))
            a.call("putc")
        a.lw(a0, s6, 0x0C)
        a.call("puthex")
        a.addi(a0, x0, 10)
        a.call("putc")
        for ch in f"T{i}:":
            a.addi(a0, x0, ord(ch))
            a.call("putc")
        a.lw(a0, s6, 0x10)
        a.call("puthex")
        a.addi(a0, x0, 10)
        a.call("putc")

    for ch in "PW:":
        a.addi(a0, x0, ord(ch))
        a.call("putc")
    a.mv(a0, s7)
    a.call("puthex")
    a.addi(a0, x0, 10)
    a.call("putc")

    for ch in "DONE\r\n":
        a.addi(a0, x0, ord(ch))
        a.call("putc")

    a.li(t0, 0x200000)
    a.label("_d")
    a.addi(t0, t0, -1)
    a.bne(t0, x0, "_d")
    a.j("main")
    a.resolve()
    return a.code


def run():
    crc_fw = make_crc_firmware()
    primary_fw = build_primary_firmware(crc_fw)
    print(f"CRC firmware: {len(crc_fw)} instructions")
    print(f"Primary firmware: {len(primary_fw)} instructions")
    print(f"Expected CRCs: {['0x%08X' % c for c in EXPECTED_CRCS]}")

    modules = ["coproc", "coproc1", "coproc2"]
    plan = validate_composition(modules)
    print(f"Composition: {plan.total_luts}/{plan.available_luts} LUTs")

    mem_words = max(1024, ((len(primary_fw) + 63) // 64) * 64)
    top_sv = compose(plan, primary_fw, mem_words=mem_words)
    out_dir = MODULES_ROOT / "compositions"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "top.sv").write_text(top_sv, encoding="utf-8")
    write_firmware_hex(primary_fw, out_dir / "firmware.hex", mem_words=mem_words)

    print("Building...")
    bitstream = build_project("compositions", clean=True)
    print(f"Built: {bitstream}")

    from icepi_admin import (  # noqa: E402
        _pnputil_switch_to_jtag, _pnputil_switch_to_uart,
        probe_jtag_target, run_loader_command,
    )
    import serial  # noqa: E402
    import serial.tools.list_ports  # noqa: E402

    _pnputil_switch_to_jtag()
    time.sleep(3)
    for _ in range(6):
        if probe_jtag_target():
            break
        time.sleep(2)
    run_loader_command(["-b", "icepi-zero", str(bitstream)], check=True)
    _pnputil_switch_to_uart()
    time.sleep(5)

    port = next(
        (p.device for p in serial.tools.list_ports.comports()
         if "0403" in (p.hwid or "")),
        None,
    )
    silicon = {}
    if port:
        with serial.Serial(port, 115200, timeout=60) as ser:
            buf = bytearray()
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                chunk = ser.read(ser.in_waiting or 1)
                if chunk:
                    buf.extend(chunk)
                if buf.decode("ascii", errors="replace").count("DONE") >= 2:
                    break
                time.sleep(0.01)
            for line in buf.decode("ascii", errors="replace").splitlines():
                line = line.strip()
                if line and ":" in line and line[0].isalpha():
                    k, _, v = line.partition(":")
                    try:
                        silicon[k.strip()] = int(v.strip(), 16)
                    except ValueError:
                        pass

    from compositor_test import restore_rime  # noqa: E402
    restore_rime()

    print()
    print("=== COPROC PARALLEL REGRESSION ===")
    failures = 0

    for i in range(N_SEGMENTS):
        s = silicon.get(f"C{i}")
        exp = EXPECTED_CRCS[i]
        cycles = silicon.get(f"T{i}", 0)
        if s is None:
            print(f"  Seg{i}: MISSING")
            failures += 1
        elif s != exp:
            print(f"  Seg{i}: FAIL silicon=0x{s:08X} expected=0x{exp:08X} cycles={cycles}")
            failures += 1
        else:
            print(f"  Seg{i}: PASS 0x{s:08X} cycles={cycles}")

    pw = silicon.get("PW", 0)
    t_vals = [silicon.get(f"T{i}", 0) for i in range(N_SEGMENTS)]
    max_t = max(t_vals) if t_vals else 0
    sum_t = sum(t_vals)

    print(f"\n  Primary wait: {pw} iterations")
    print(f"  Coprocessor cycles: {t_vals}")
    print(f"  Sum: {sum_t}  Max: {max_t}")

    if max_t > 0 and sum_t > 0:
        speedup = sum_t / max_t
        print(f"  Speedup: {speedup:.2f}x")
        if speedup < 2.5:
            print(f"  FAIL: speedup {speedup:.2f}x < 2.5x minimum")
            failures += 1
    else:
        print("  FAIL: no cycle data")
        failures += 1

    crcs = [silicon.get(f"C{i}") for i in range(N_SEGMENTS)]
    if len(set(c for c in crcs if c is not None)) < N_SEGMENTS:
        print("  FAIL: not all segment CRCs are distinct")
        failures += 1

    if failures == 0:
        print("\n  COPROC REGRESSION: PASS")
    else:
        print(f"\n  COPROC REGRESSION: FAIL ({failures} failures)")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
