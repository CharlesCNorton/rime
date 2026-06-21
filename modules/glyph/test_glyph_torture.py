#!/usr/bin/env python3
"""Torture test for GLYPH: GLYPH: Galois Logic for Yielding Polynomial Hashes. GF(2^8) matrix multiplier.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

OP_A   = 0x000
OP_B   = 0x004
MUL    = 0x008
INV    = 0x00C
EXP    = 0x010
CTRL   = 0x014
STATUS = 0x018


def gen():
    tb = TortureBuilder("glyph")
    # GF(2^8) identity tests using read_assert.
    # 0 * anything = 0
    tb.write(OP_A, 0)
    tb.write(OP_B, 0xFF)
    tb.read_assert(MUL, 0)
    # anything * 0 = 0
    tb.write(OP_A, 0xA5)
    tb.write(OP_B, 0)
    tb.read_assert(MUL, 0)
    # 1 * x = x (for any x)
    tb.write(OP_A, 1)
    tb.write(OP_B, 0x42)
    tb.read_assert(MUL, 0x42)
    # x * 1 = x
    tb.write(OP_A, 0x99)
    tb.write(OP_B, 1)
    tb.read_assert(MUL, 0x99)
    # inverse of 1 is 1
    tb.write(OP_A, 1)
    tb.read_assert(INV, 1)
    # AES S-box known: inv(0) = 0 by convention
    tb.write(OP_A, 0)
    tb.read_assert(INV, 0)

    tb.write(0x000, 0x02)
    tb.write(0x004, 0x03)
    tb.read_check(0x008, 0x06)
    tb.write(0x000, 0x53)
    tb.read_mix(0x00C, None)
    tb.write(0x000, 0x02)
    tb.write(0x004, 0x08)
    tb.write(0x014, 1)
    tb.delay(20)
    tb.read_check(0x018, 1)
    tb.read_mix(0x010, None)
    tb.write(0x000, 0x00)
    tb.write(0x004, 0xFF)
    tb.read_check(0x008, 0)
    tb.write(0x000, 0x01)
    tb.write(0x004, 0xAB)
    tb.read_check(0x008, 0xAB)
    tb.adversarial_write(0x008, 0xDEAD)
    tb.adversarial_write(0x00C, 0xBEEF)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"GLYPH torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("glyph", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("glyph", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("glyph")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
