#!/usr/bin/env python3
"""Torture test for GPIO: GPIO: General Purpose Input/Output — 16 software-driven pins with direction, output, input, edge detect

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

DIR     = 0x000
OUT     = 0x004
IN      = 0x008
PIN     = 0x00C
EDGE    = 0x010
CONTROL = 0x014


def gen():
    tb = TortureBuilder("gpio")
    # Set all pins as input, drive sim input, read pin
    tb.write(DIR, 0)
    tb.write(IN, 0xAAAA)
    tb.read_check(PIN, 0xAAAA)
    # Set all as output, drive output
    tb.write(DIR, 0xFFFF)
    tb.write(OUT, 0x5555)
    tb.read_check(PIN, 0x5555)
    # Mix: half input half output
    tb.write(DIR, 0xFF00)
    tb.write(OUT, 0x5500)
    tb.write(IN, 0x00AA)
    tb.read_check(PIN, 0x55AA)
    # Reset
    tb.write(DIR, 0)
    tb.write(IN, 0)
    tb.read_check(PIN, 0)

    tb.write(0x014, 1)
    tb.write(0x000, 0xFFFF)
    tb.write(0x004, 0xAAAA)
    tb.read_check(0x000, 0xFFFF)
    tb.read_check(0x004, 0xAAAA)
    tb.read_check(0x00C, 0xAAAA)
    tb.write(0x000, 0x0000)
    tb.write(0x008, 0x5555)
    tb.read_check(0x00C, 0x5555)
    tb.write(0x008, 0xFFFF)
    tb.delay(3)
    tb.read_mix(0x010, None)
    tb.adversarial_write(0x00C, 0)
    tb.adversarial_write(0x010, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"GPIO torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
