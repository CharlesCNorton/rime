#!/usr/bin/env python3
"""Torture test for LATCH: LATCH: hardware watchdog timer + event counter.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("latch")
    tb.write(0x008, 7)
    tb.write(0x00C, 1000)
    tb.write(0x000, 1)
    tb.read_mix(0x004, None)
    tb.read_mix(0x010, None)
    tb.write(0x014, 1)
    tb.write(0x014, 1)
    tb.write(0x014, 1)
    tb.read_check(0x018, 3)
    tb.read_mix(0x01C, None)
    tb.write(0x008, 7)
    tb.read_check(0x018, 0)

    tb.write(0x008, 4)
    tb.read_check(0x018, 0)
    for _ in range(8):
        tb.write(0x014, 1)
    tb.read_check(0x018, 8)
    tb.adversarial_write(0x004, 0xFFFFFFFF)
    tb.adversarial_write(0x010, 0xDEADBEEF)
    tb.adversarial_write(0x018, 0)
    tb.read_check(0x018, 8)
    tb.write(0x00C, 1)
    tb.write(0x008, 1)
    tb.write(0x000, 1)
    tb.delay(20)
    tb.read_mix(0x004, None)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"LATCH torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("latch", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("latch", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("latch")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
