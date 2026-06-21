#!/usr/bin/env python3
"""Torture test for PULSE: PULSE: Programmable Unified Logic for Signal Emission — 4-channel 16-bit PWM generator

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder


def gen():
    tb = TortureBuilder("pulse")
    # Reset, configure ch0 period=10 duty=5
    tb.write(0x024, 2)              # reset counters
    tb.write(0x000, 10)             # period
    tb.write(0x004, 5)              # duty
    tb.read_check(0x000, 10)
    tb.read_check(0x004, 5)
    # Read OUTPUT (should be 0 since not enabled)
    tb.read_check(0x020, 0)
    # Enable
    tb.write(0x024, 1)
    tb.delay(50)
    tb.read_mix(0x020)
    tb.read_mix(0x028)

    # Adversarial: configure all 4 channels with boundary values
    tb.write(0x024, 2)  # reset
    for ch in range(4):
        tb.write(ch * 8 + 0x000, 0xFFFF)  # max period
        tb.write(ch * 8 + 0x004, 0x0000)  # zero duty (always low)
        tb.read_check(ch * 8 + 0x000, 0xFFFF)
        tb.read_check(ch * 8 + 0x004, 0x0000)
    tb.write(0x024, 1)  # enable
    tb.delay(20)
    tb.read_check(0x020, 0)  # all channels low (zero duty)

    # Set duty = period (always high)
    tb.write(0x024, 2)  # reset
    for ch in range(4):
        tb.write(ch * 8 + 0x000, 100)
        tb.write(ch * 8 + 0x004, 100)
    tb.write(0x024, 1)  # enable
    tb.delay(20)
    tb.read_check(0x020, 0x0F)  # all channels high

    # Adversarial: garbage writes to read-only registers
    tb.adversarial_write(0x020, 0xFFFFFFFF)
    tb.adversarial_write(0x028, 0xDEADBEEF)
    tb.read_check(0x020, 0x0F)  # unchanged

    # Rapid duty changes while running
    tb.write(0x004, 1)   # duty=1
    tb.write(0x004, 50)  # duty=50
    tb.write(0x004, 99)  # duty=99
    tb.read_check(0x004, 99)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"PULSE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
