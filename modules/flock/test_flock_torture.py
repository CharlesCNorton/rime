#!/usr/bin/env python3
"""FLOCK hash-based torture test.

Steps the boids simulation, reads agent positions and step counts.
Step count is deterministic
positions depend on the simulation but
the step-count checks differentiate this from other modules.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

STEP   = 0x000
STATUS = 0x004
RESET  = 0x008
X0     = 0x010
Y0     = 0x014
X1     = 0x018
X2     = 0x020

def gen():
    tb = TortureBuilder("flock")

    # Reset
    tb.write(RESET, 1)
    tb.read_check(STATUS, 0)

    # Initial position after reset
    tb.read_mix(X0, None)

    # Step 5 times
    for _ in range(5):
        tb.write(STEP, 1)
    tb.read_check(STATUS, 5)
    tb.read_mix(X0, None)
    tb.read_mix(Y0, None)
    tb.read_mix(X1, None)

    # Step 15 more
    for _ in range(15):
        tb.write(STEP, 1)
    tb.read_check(STATUS, 20)
    tb.read_mix(X0, None)
    tb.read_mix(X2, None)

    # Reset and verify
    tb.write(RESET, 1)
    tb.read_check(STATUS, 0)
    tb.read_mix(X0, None)

    # Step once
    tb.write(STEP, 1)
    tb.read_check(STATUS, 1)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"FLOCK torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("flock", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("flock", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("flock")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
