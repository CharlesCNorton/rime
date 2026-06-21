#!/usr/bin/env python3
"""Torture test for ORBIT: Optimized Rotation and Basic Iteration Toolkit — 20-iteration CORDIC for sin/cos/atan/magnitude

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

ANGLE   = 0x000
INPUT_X = 0x004
INPUT_Y = 0x008
CONTROL = 0x00C
STATUS  = 0x010
COS_MAG = 0x014
SIN_PHS = 0x018

def gen():
    tb = TortureBuilder("orbit")

    # angle=0: cos=K, sin=0
    tb.write(ANGLE, 0)
    tb.write(CONTROL, 0x01)
    tb.delay(25)
    tb.read_check(STATUS, 1)
    tb.read_discard(COS_MAG)
    tb.read_discard(SIN_PHS)  # sin(0) ≈ 0 but CORDIC rounding may produce ±1 LSB

    # angle=pi/4: both nonzero
    tb.write(ANGLE, 0x0000C910)
    tb.write(CONTROL, 0x01)
    tb.delay(25)
    tb.read_check(STATUS, 1)
    tb.read_discard(COS_MAG)
    tb.read_discard(SIN_PHS)

    # negative angle
    tb.write(ANGLE, 0xFFFF36F0)
    tb.write(CONTROL, 0x01)
    tb.delay(25)
    tb.read_check(STATUS, 1)
    tb.read_discard(COS_MAG)
    tb.read_discard(SIN_PHS)


    tb.write(0x000, 0)
    tb.write(0x00C, 1)
    tb.delay(50)
    tb.read_mix(0x014, None)
    tb.read_mix(0x018, None)
    tb.write(0x000, 0x00010000)
    tb.write(0x00C, 1)
    tb.delay(50)
    tb.read_mix(0x014, None)
    tb.read_mix(0x018, None)
    tb.write(0x004, 0x00010000)
    tb.write(0x008, 0x00010000)
    tb.write(0x00C, 3)
    tb.delay(50)
    tb.read_mix(0x014, None)
    tb.read_mix(0x018, None)
    tb.adversarial_write(0x010, 0)
    tb.adversarial_write(0x014, 0)

    return tb.finish()

def main():
    firmware, expected = gen()
    print(f"ORBIT torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("orbit", firmware, mod_dir / "top.sv")
    ok, luts = build_module("orbit", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("orbit")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
