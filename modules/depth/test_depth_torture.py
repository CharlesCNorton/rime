#!/usr/bin/env python3
"""Torture test for DEPTH: DEPTH: Dynamic Execution Profile and Thread Height tracker — stack pointer min/max via snoop

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

SP_BASE = 0x000
SP_MASK = 0x004
SP_MIN  = 0x008
SP_MAX  = 0x00C
SAMPLES = 0x010
LAST_SP = 0x014
CONTROL = 0x018


def gen():
    tb = TortureBuilder("depth")
    tb.write(CONTROL, 0x01)  # reset
    tb.read_check(SP_MIN, 0xFFFFFFFF)
    tb.read_check(SP_MAX, 0)
    tb.read_check(SAMPLES, 0)

    # Configure base/mask and enable
    tb.write(SP_BASE, 0x00000000)
    tb.write(SP_MASK, 0xFFFFF000)
    tb.write(CONTROL, 0x03)  # reset + enable

    # Snoop-based tracking won't fire from register writes alone,
    # but we verify register state machine
    tb.read_mix(SP_MIN)
    tb.read_mix(SP_MAX)
    tb.read_mix(SAMPLES)

    # Reset
    tb.write(CONTROL, 0x01)
    tb.read_check(SAMPLES, 0)


    tb.write(0x018, 1)
    tb.write(0x000, 0x00000FFC)
    tb.write(0x004, 0xFFFFFF00)
    tb.write(0x018, 2)
    tb.delay(10)
    tb.read_mix(0x008, None)
    tb.read_mix(0x00C, None)
    tb.read_mix(0x010, None)
    tb.adversarial_write(0x008, 0)
    tb.adversarial_write(0x00C, 0)
    tb.adversarial_write(0x010, 0)
    tb.write(0x018, 1)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"DEPTH torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("depth", firmware, mod_dir / "top.sv")
    ok, luts = build_module("depth", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("depth")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
