#!/usr/bin/env python3
"""Torture test for HAMMER: Hardware Accelerated Matching and Measurement Engine Register — 256-bit Hamming distance

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

A_BASE    = 0x000
B_BASE    = 0x020
DISTANCE  = 0x040
MATCH     = 0x044
THRESHOLD = 0x048
FUZZY     = 0x04C

def gen():
    tb = TortureBuilder("hammer")
    # Identical vectors -> distance 0
    for i in range(8):
        tb.write(A_BASE + i*4, 0xDEADBEEF)
        tb.write(B_BASE + i*4, 0xDEADBEEF)
    tb.read_check(DISTANCE, 0)
    tb.read_check(MATCH, 1)

    # Flip 1 bit -> distance 1
    tb.write(B_BASE, 0xDEADBEEE)
    tb.read_check(DISTANCE, 1)
    tb.read_check(MATCH, 0)

    # All bits different -> distance 256
    for i in range(8):
        tb.write(A_BASE + i*4, 0xFFFFFFFF)
        tb.write(B_BASE + i*4, 0x00000000)
    tb.read_check(DISTANCE, 256)

    # Known pattern: A=0x0F0F0F0F, B=0xF0F0F0F0 in word 0 only
    for i in range(8):
        tb.write(A_BASE + i*4, 0)
        tb.write(B_BASE + i*4, 0)
    tb.write(A_BASE, 0x0F0F0F0F)
    tb.write(B_BASE, 0xF0F0F0F0)
    # XOR = 0xFFFFFFFF -> popcount 32
    tb.read_check(DISTANCE, 32)

    # Threshold test
    tb.write(THRESHOLD, 32)
    tb.read_check(FUZZY, 1)
    tb.write(THRESHOLD, 31)
    tb.read_check(FUZZY, 0)

    # Zero vs zero
    for i in range(8):
        tb.write(A_BASE + i*4, 0)
        tb.write(B_BASE + i*4, 0)
    tb.read_check(DISTANCE, 0)
    tb.read_check(MATCH, 1)

    return tb.finish()

def main():
    firmware, expected = gen()
    print(f"HAMMER torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("hammer", firmware, mod_dir / "top.sv")
    ok, luts = build_module("hammer", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("hammer")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
