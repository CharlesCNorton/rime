#!/usr/bin/env python3
"""AUGUR hash-based torture test.

Exercises MCMC sampler: set target, step chains, read step/accept counts,
change target, step again. Differentiates from other timing-dependent
modules by using multiple target values and checking step counts.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

CHAIN0  = 0x000
CHAIN1  = 0x004
CONTROL = 0x010
STEPS   = 0x014
ACCEPTS = 0x018
MEAN    = 0x01C
TARGET  = 0x020

def gen():
    tb = TortureBuilder("augur")

    # Set target and reset
    tb.write(TARGET, 1000)
    tb.write(CONTROL, 2)  # reset
    tb.read_check(STEPS, 0)

    # Step 10 times
    for _ in range(10):
        tb.write(CONTROL, 1)
    tb.read_check(STEPS, 10)
    tb.read_mix(ACCEPTS, None)
    tb.read_mix(CHAIN0, None)
    tb.read_mix(CHAIN1, None)
    tb.read_mix(MEAN, None)

    # Change target, step 10 more
    tb.write(TARGET, 50000)
    for _ in range(10):
        tb.write(CONTROL, 1)
    tb.read_check(STEPS, 20)
    tb.read_mix(ACCEPTS, None)
    tb.read_mix(CHAIN0, None)

    # Adversarial target + reset
    tb.adversarial_write(TARGET, 0xFFFFFFFF)
    tb.write(CONTROL, 2)
    tb.read_check(STEPS, 0)
    tb.write(CONTROL, 1)
    tb.read_check(STEPS, 1)

    return tb.finish()

def main():
    fw, exp = gen()
    print(f"AUGUR torture: {len(fw)} instrs, expected 0x{exp:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    generate_top_sv("augur", fw, Path(__file__).resolve().parent / "top.sv")
    ok, _ = build_module("augur", fw)
    if not ok:
        print("BUILD FAILED")
    restore_rime()
    return 1
    output = flash_and_read("augur")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split(chr(10))[0] else 1

if __name__ == "__main__":
    raise SystemExit(main())
