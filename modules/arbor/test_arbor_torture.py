#!/usr/bin/env python3
"""Torture test for ARBOR: ARBOR: Arbitrated Routing for Board-level Ordered Requests — 16-source priority interrupt controller

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder


def gen():
    tb = TortureBuilder("arbor")
    tb.write(0x010, 1)             # clear all
    tb.read_check(0x000, 0)
    # Raise sources 3 and 7
    tb.write(0x014, 3)
    tb.write(0x014, 7)
    tb.read_check(0x000, (1 << 3) | (1 << 7))
    # Mask in all
    tb.write(0x004, 0xFFFF)
    tb.read_check(0x00C, 1)        # any pending
    # Claim should return 7 (highest)
    tb.read_check(0x008, 7)
    # After claim, bit 7 cleared
    tb.read_check(0x000, 1 << 3)
    # Claim again returns 3
    tb.read_check(0x008, 3)
    # Now nothing pending — claim returns 16
    tb.read_check(0x008, 16)

    # Adversarial: raise all 16 sources, claim in priority order
    tb.write(0x010, 1)  # clear all
    for i in range(16):
        tb.write(0x014, i)
    tb.write(0x004, 0xFFFF)  # mask in all
    tb.read_check(0x00C, 1)  # any pending
    # Claim should return 15 (highest priority), then 14, ..., 0
    for i in range(15, -1, -1):
        tb.read_check(0x008, i)
    tb.read_check(0x008, 16)  # empty

    # Adversarial: mask interaction
    tb.write(0x010, 1)  # clear
    tb.write(0x014, 5)  # raise source 5
    tb.write(0x014, 10) # raise source 10
    tb.write(0x004, 1 << 5)  # mask only source 5
    tb.read_check(0x00C, 1)  # something pending
    tb.read_check(0x008, 5)  # claim returns 5 (10 is masked out)
    tb.read_check(0x008, 16) # nothing left (10 is pending but masked)

    # Adversarial: garbage to read-only
    tb.adversarial_write(0x000, 0xFFFFFFFF)
    tb.adversarial_write(0x00C, 0xDEADBEEF)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"ARBOR torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
