#!/usr/bin/env python3
"""EMBERLITE hash-based torture test.

Exercises the hardware entropy source: reset, read random words,
check COUNT increments, reset again, verify COUNT clears. The
random values are unpredictable but COUNT is deterministic.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

RANDOM  = 0x000
BYTE    = 0x004
CONTROL = 0x008
COUNT   = 0x00C

def gen():
    tb = TortureBuilder("emberlite")

    # Reset
    tb.reset(CONTROL, bit=0)
    tb.read_check(COUNT, 0)

    # Read entropy several times — values unpredictable
    tb.read_mix(RANDOM, None)
    tb.read_mix(RANDOM, None)
    tb.read_mix(RANDOM, None)
    tb.read_mix(BYTE, None)

    # COUNT should have advanced (ring oscillators produce bits continuously)
    tb.read_mix(COUNT, None)

    # Reset and verify COUNT clears
    tb.reset(CONTROL, bit=0)
    tb.read_check(COUNT, 0)

    # Read more entropy
    tb.read_mix(RANDOM, None)
    tb.read_mix(RANDOM, None)
    tb.read_mix(BYTE, None)
    tb.read_mix(COUNT, None)

    # Final reset
    tb.reset(CONTROL, bit=0)
    tb.read_check(COUNT, 0)


    tb.write(0x008, 1)
    tb.delay(20)
    tb.read_mix(0x000, None)
    tb.read_mix(0x004, None)
    tb.read_mix(0x010, None)
    tb.read_mix(0x00C, None)
    tb.adversarial_write(0x000, 0xFFFFFFFF)
    tb.adversarial_write(0x004, 0)
    tb.adversarial_write(0x00C, 0)
    tb.adversarial_write(0x010, 0)
    tb.write(0x008, 1)
    tb.delay(20)
    tb.read_mix(0x000, None)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"EMBERLITE torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("emberlite", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("emberlite", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("emberlite")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
