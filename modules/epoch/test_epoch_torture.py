#!/usr/bin/env python3
"""Torture test for EPOCH: EPOCH: real-time clock synthesizer from sys_clk.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("epoch")
    tb.write(0x010, 3)
    tb.read_check(0x000, 0)
    tb.read_check(0x004, 0)
    tb.write(0x000, 59)
    tb.write(0x004, 58)
    tb.read_check(0x000, 59)
    tb.read_check(0x004, 58)
    tb.read_mix(0x014, None)
    tb.read_mix(0x018, None)
    tb.adversarial_write(0x000, 0xFFFFFFFF)
    tb.write(0x010, 3)
    tb.read_check(0x000, 0)

    tb.write(0x010, 2)
    tb.write(0x000, 59)
    tb.write(0x004, 59)
    tb.write(0x008, 23)
    tb.write(0x00C, 0xFFFF)
    tb.read_check(0x000, 59)
    tb.read_check(0x004, 59)
    tb.read_check(0x008, 23)
    tb.read_check(0x00C, 0xFFFF)
    tb.adversarial_write(0x014, 0xFFFFFFFF)
    tb.adversarial_write(0x018, 0xDEADBEEF)
    tb.write(0x010, 1)
    tb.delay(10)
    tb.read_mix(0x014, None)
    tb.write(0x010, 2)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"EPOCH torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("epoch", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("epoch", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("epoch")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
