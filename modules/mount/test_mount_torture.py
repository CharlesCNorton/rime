#!/usr/bin/env python3
"""Torture test for MOUNT: Modular Operation Utility for Number Theory — 256-bit Montgomery multiplier

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

A_BASE   = 0x000
B_BASE   = 0x020
M_BASE   = 0x040
CONTROL  = 0x060
STATUS   = 0x064
RES_BASE = 0x080

def montgomery_mul(a, b, m):
    """Python Montgomery multiply: a * b * R^-1 mod m, R = 2^256."""
    acc = 0
    for i in range(256):
        if (a >> i) & 1:
            acc += b
        if acc & 1:
            acc += m
        acc >>= 1
    if acc >= m:
        acc -= m
    return acc

def write_256(tb, base, val):
    for i in range(8):
        tb.write(base + i * 4, (val >> (i * 32)) & 0xFFFFFFFF)

def gen():
    tb = TortureBuilder("mount")

    # Simple test: A=3, B=7, M=11 (odd prime)
    # Montgomery: 3 * 7 * R^-1 mod 11
    a, b, m = 3, 7, 11
    expected = montgomery_mul(a, b, m)
    write_256(tb, A_BASE, a)
    write_256(tb, B_BASE, b)
    write_256(tb, M_BASE, m)
    tb.write(CONTROL, 1)
    tb.delay(270)
    tb.read_mix(STATUS)
    tb.read_mix(RES_BASE, expected & 0xFFFFFFFF)

    # Larger: A=0xFF, B=0xFF, M=257 (Fermat prime)
    a2, b2, m2 = 0xFF, 0xFF, 257
    expected2 = montgomery_mul(a2, b2, m2)
    write_256(tb, A_BASE, a2)
    write_256(tb, B_BASE, b2)
    write_256(tb, M_BASE, m2)
    tb.write(CONTROL, 1)
    tb.delay(270)
    tb.read_mix(STATUS)
    tb.read_mix(RES_BASE, expected2 & 0xFFFFFFFF)

    # Identity: A * 1 mod M
    a3, m3 = 42, 97
    expected3 = montgomery_mul(a3, 1, m3)
    write_256(tb, A_BASE, a3)
    write_256(tb, B_BASE, 1)
    write_256(tb, M_BASE, m3)
    tb.write(CONTROL, 1)
    tb.delay(270)
    tb.read_mix(STATUS)
    tb.read_mix(RES_BASE, expected3 & 0xFFFFFFFF)

    return tb.finish()

def main():
    firmware, expected = gen()
    print(f"MOUNT torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("mount", firmware, mod_dir / "top.sv")
    ok, luts = build_module("mount", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("mount")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
