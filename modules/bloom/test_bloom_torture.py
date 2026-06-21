#!/usr/bin/env python3
"""BLOOM hash-based torture test.

Exercises all bit operations: popcount, CLZ, CTZ, bit reverse, parity.
Adversarial: all-zeros, all-ones, single-bit, alternating patterns,
powers of two, edge values.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

INPUT   = 0x000
POPCNT  = 0x004
CLZ     = 0x008
CTZ     = 0x00C
REVERSE = 0x010
PARITY  = 0x014


def ref_popcnt(v):
    return bin(v & 0xFFFFFFFF).count('1')

def ref_clz(v):
    v = v & 0xFFFFFFFF
    if v == 0:
        return 32
    n = 0
    while not (v & 0x80000000):
        n += 1
        v <<= 1
    return n

def ref_ctz(v):
    v = v & 0xFFFFFFFF
    if v == 0:
        return 32
    n = 0
    while not (v & 1):
        n += 1
        v >>= 1
    return n

def ref_reverse(v):
    v = v & 0xFFFFFFFF
    r = 0
    for i in range(32):
        r |= ((v >> i) & 1) << (31 - i)
    return r

def ref_parity(v):
    v = v & 0xFFFFFFFF
    p = 0
    while v:
        p ^= v & 1
        v >>= 1
    return p


def gen():
    tb = TortureBuilder("bloom")

    test_values = [
        0x00000000,
        0xFFFFFFFF,
        0x00000001,
        0x80000000,
        0x55555555,
        0xAAAAAAAA,
        0x0F0F0F0F,
        0xF0F0F0F0,
        0x00010000,
        0x0000FFFF,
        0xFFFF0000,
        0xDEADBEEF,
        0x12345678,
        0x00000080,
        0x7FFFFFFF,
        0x00008000,
    ]

    for v in test_values:
        tb.write(INPUT, v)
        tb.read_check(POPCNT, ref_popcnt(v))
        tb.read_check(CLZ, ref_clz(v))
        tb.read_check(CTZ, ref_ctz(v))
        tb.read_check(REVERSE, ref_reverse(v))
        tb.read_check(PARITY, ref_parity(v))

    # Adversarial: selected single-bit values (boundary positions)
    for bit in [0, 1, 15, 16, 30, 31]:
        v = 1 << bit
        tb.write(INPUT, v)
        tb.read_check(POPCNT, 1)
        tb.read_check(CLZ, 31 - bit)
        tb.read_check(CTZ, bit)

    # Adversarial: rapid writes without reads (last write wins)
    tb.write(INPUT, 0x11111111)
    tb.write(INPUT, 0x22222222)
    tb.write(INPUT, 0x33333333)
    tb.read_check(POPCNT, ref_popcnt(0x33333333))

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"BLOOM torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("bloom", firmware, mod_dir / "top.sv")
    ok, luts = build_module("bloom", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("bloom")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
