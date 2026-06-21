#!/usr/bin/env python3
"""Torture test for PYLON: PYLON: Paired Yield-Linked Output Node — 8-deep × 32-bit FIFO mailbox between two software-driven ports

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder


def gen():
    tb = TortureBuilder("pylon")
    tb.write(0x014, 1)             # clear
    tb.read_check(0x010, 0)
    tb.read_check(0x00C, 1)        # empty
    # Push 3 values
    tb.write(0x000, 0xAA)
    tb.write(0x000, 0xBB)
    tb.write(0x000, 0xCC)
    tb.read_check(0x010, 3)        # count
    tb.read_check(0x008, 0xAA)     # peek
    # Pop in order
    tb.read_check(0x004, 0xAA)
    tb.read_check(0x004, 0xBB)
    tb.read_check(0x004, 0xCC)
    tb.read_check(0x010, 0)
    tb.read_check(0x00C, 1)        # empty again

    tb.write(0x014, 1)
    tb.read_check(0x010, 0)
    for v in [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]:
        tb.write(0x000, v)
    tb.read_check(0x010, 8)
    tb.read_check(0x008, 0x11)
    tb.read_check(0x004, 0x11)
    tb.read_check(0x004, 0x22)
    tb.read_check(0x010, 6)
    tb.write(0x014, 1)
    tb.read_check(0x010, 0)
    tb.adversarial_write(0x004, 0xDEADBEEF)
    tb.adversarial_write(0x010, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"PYLON torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
