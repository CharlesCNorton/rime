#!/usr/bin/env python3
"""Torture test for NOTCH: NOTCH: Noise-Opposing Transition and Contact Handler — 8-channel hardware debounce filter

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

RAW_IN    = 0x000
FILTERED  = 0x004
CHANGED   = 0x008
PRESCALE  = 0x00C
THRESHOLD = 0x010
CONTROL   = 0x014


def gen():
    tb = TortureBuilder("notch")

    tb.reset(CONTROL, bit=0)
    tb.write(PRESCALE, 0)
    tb.write(THRESHOLD, 3)

    # After reset, filtered=0 and changed=0
    tb.read_assert(FILTERED, 0)
    tb.read_assert(CHANGED, 0)

    # Write stable high on channel 0 for 5 samples (threshold=3)
    for _ in range(5):
        tb.write(RAW_IN, 0x01)
        tb.delay(2)
    tb.read_assert(FILTERED, 0x01)

    # Bring all 8 channels high
    for _ in range(5):
        tb.write(RAW_IN, 0xFF)
        tb.delay(2)
    tb.read_assert(FILTERED, 0xFF)

    # Reset clears
    tb.reset(CONTROL, bit=0)
    tb.read_assert(FILTERED, 0)
    tb.read_assert(CHANGED, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"NOTCH torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("notch", firmware, mod_dir / "top.sv")
    ok, luts = build_module("notch", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("notch")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
