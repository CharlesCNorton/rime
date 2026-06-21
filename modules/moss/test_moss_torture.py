#!/usr/bin/env python3
"""Torture test for MOSS: MOSS: Massively Orchestrated Spatial Stepper. 8x8 cellular automaton.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("moss")
    tb.write(0x020, 2)
    tb.read_check(0x024, 0)
    tb.read_check(0x028, 0)
    tb.write(0x000, 0x18)
    tb.write(0x004, 0x18)
    tb.write(0x008, 0x18)
    tb.read_mix(0x028, None)
    tb.write(0x020, 1)
    tb.read_check(0x024, 1)
    tb.read_mix(0x028, None)
    for _ in range(5):
        tb.write(0x020, 1)
    tb.read_mix(0x024, None)
    tb.write(0x020, 2)
    tb.read_check(0x028, 0)

    tb.write(0x020, 2)
    tb.read_check(0x024, 0)
    tb.read_check(0x028, 0)
    tb.write(0x000, 0x07)
    tb.write(0x020, 1)
    tb.delay(5)
    tb.read_check(0x024, 1)
    tb.read_mix(0x028, None)
    tb.read_mix(0x000, None)
    tb.read_mix(0x004, None)
    tb.write(0x020, 1)
    tb.delay(5)
    tb.read_mix(0x000, None)
    tb.read_check(0x024, 2)
    tb.adversarial_write(0x024, 0)
    tb.adversarial_write(0x028, 0)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"MOSS torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("moss", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("moss", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("moss")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
