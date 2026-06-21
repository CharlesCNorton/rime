#!/usr/bin/env python3
"""Torture test for SIFT: SIFT: Set Intersection Filter Tile. Hardware Bloom filter.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("sift")
    tb.write(0x008, 1)
    tb.read_check(0x00C, 0)
    tb.read_check(0x010, 0)
    tb.write(0x000, 0x12345678)
    tb.write(0x000, 0xDEADBEEF)
    tb.read_check(0x00C, 2)
    tb.read_mix(0x010, None)
    tb.write(0x004, 0x12345678)
    tb.read_check(0x004, 1)
    tb.write(0x008, 1)
    tb.read_check(0x010, 0)

    tb.write(0x008, 1)
    tb.read_check(0x00C, 0)
    tb.read_check(0x010, 0)
    for v in [0, 1, 0xFF, 0x1234, 0xFFFFFFFF, 0x80000000]:
        tb.write(0x000, v)
    tb.read_check(0x00C, 6)
    tb.read_mix(0x010, None)
    tb.write(0x004, 0)
    tb.read_mix(0x004, None)
    tb.write(0x004, 0xFFFFFFFF)
    tb.read_mix(0x004, None)
    tb.adversarial_write(0x00C, 0)
    tb.adversarial_write(0x010, 0)
    tb.read_check(0x00C, 6)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"SIFT torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("sift", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("sift", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("sift")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
