#!/usr/bin/env python3
"""Torture test for TIDE: TIDE: DDS waveform generator with phase accumulator.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("tide")
    tb.write(0x010, 3)
    tb.write(0x000, 0)
    tb.write(0x004, 0)
    tb.write(0x010, 1)
    tb.read_check(0x008, 128)
    tb.write(0x004, 1)
    tb.read_mix(0x008, None)
    tb.write(0x004, 2)
    tb.read_mix(0x008, None)
    tb.write(0x004, 3)
    tb.read_mix(0x008, None)
    tb.write(0x000, 0x10000000)
    tb.delay(50)
    tb.read_mix(0x008, None)

    tb.write(0x010, 2)
    tb.write(0x000, 0x01000000)
    tb.write(0x004, 0)
    tb.write(0x010, 1)
    tb.delay(20)
    tb.read_mix(0x008, None)
    tb.write(0x004, 1)
    tb.delay(10)
    tb.read_mix(0x008, None)
    tb.write(0x004, 2)
    tb.delay(10)
    tb.read_mix(0x008, None)
    tb.write(0x004, 3)
    tb.delay(10)
    tb.read_mix(0x008, None)
    tb.write(0x00C, 0x80000000)
    tb.read_check(0x00C, 0x80000000)
    tb.adversarial_write(0x008, 0xDEAD)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"TIDE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("tide", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("tide", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("tide")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
