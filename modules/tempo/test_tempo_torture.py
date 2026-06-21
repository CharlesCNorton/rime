#!/usr/bin/env python3
"""Torture test for TEMPO: TEMPO: Timed Event Measurement and Period Observer — frequency and period counter

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

SIGNAL  = 0x000
GATE    = 0x004
FREQ    = 0x008
PERIOD  = 0x00C
CONTROL = 0x010
STATUS  = 0x014


def gen():
    tb = TortureBuilder("tempo")

    tb.write(CONTROL, 0x02)  # reset

    # Set gate window, start gate, toggle signal a few times
    tb.write(GATE, 200)
    tb.write(CONTROL, 0x01)  # start gate
    # Generate 3 rising edges within the gate
    for _ in range(3):
        tb.write(SIGNAL, 0)
        tb.delay(5)
        tb.write(SIGNAL, 1)
        tb.delay(5)
    # Wait for gate to close
    tb.delay(200)
    tb.read_mix(FREQ)
    tb.read_mix(PERIOD)
    tb.read_mix(STATUS)

    # Reset and verify
    tb.write(CONTROL, 0x02)
    tb.read_check(FREQ, 0)


    tb.write(0x010, 2)
    tb.write(0x004, 50)
    tb.write(0x010, 1)
    tb.write(0x000, 0)
    tb.write(0x000, 1)
    tb.write(0x000, 0)
    tb.write(0x000, 1)
    tb.write(0x000, 0)
    tb.write(0x000, 1)
    tb.delay(100)
    tb.read_mix(0x008, None)
    tb.read_mix(0x00C, None)
    tb.adversarial_write(0x008, 0)
    tb.adversarial_write(0x00C, 0)
    tb.adversarial_write(0x014, 0)
    tb.write(0x010, 2)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"TEMPO torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("tempo", firmware, mod_dir / "top.sv")
    ok, luts = build_module("tempo", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("tempo")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
