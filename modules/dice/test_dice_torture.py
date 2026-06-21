#!/usr/bin/env python3
"""Torture test for DICE: DICE: Density-Inferred Computation Engine. Stochastic computing matrix.

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

def gen():
    tb = TortureBuilder("dice")
    tb.write(0x00C, 2)
    tb.write(0x000, 128)
    tb.write(0x004, 128)
    tb.write(0x00C, 1)
    tb.delay(300)
    tb.read_mix(0x008, None)
    tb.read_mix(0x014, None)
    tb.adversarial_write(0x000, 0)
    tb.adversarial_write(0x004, 0)
    tb.write(0x00C, 1)
    tb.delay(300)
    tb.read_check(0x008, 0)

    # Adversarial: boundary values
    tb.write(0x00C, 2)  # reset
    tb.write(0x000, 0xFFFF)  # max A
    tb.write(0x004, 1)       # min B
    tb.write(0x00C, 1)
    tb.delay(300)
    tb.read_mix(0x008, None)

    tb.write(0x00C, 2)  # reset
    tb.write(0x000, 1)       # min A
    tb.write(0x004, 0xFFFF)  # max B
    tb.write(0x00C, 1)
    tb.delay(300)
    tb.read_mix(0x008, None)

    # Adversarial: garbage to read-only
    tb.adversarial_write(0x008, 0xDEADBEEF)
    tb.adversarial_write(0x014, 0xFFFFFFFF)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"DICE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("dice", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("dice", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("dice")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
