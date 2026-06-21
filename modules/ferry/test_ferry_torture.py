#!/usr/bin/env python3
"""Torture test for FERRY: FERRY: Fast External Register Relay Engine — 8-word internal scratchpad copy with src/dst/count programming

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder


def gen():
    tb = TortureBuilder("ferry")
    tb.write(0x04C, 2)             # reset
    # Load scratch[0..3] = 0xAA, 0xBB, 0xCC, 0xDD
    tb.write(0x000, 0xAA)
    tb.write(0x004, 0xBB)
    tb.write(0x008, 0xCC)
    tb.write(0x00C, 0xDD)
    # Program copy: src=0, dst=8, count=4
    tb.write(0x040, 0)
    tb.write(0x044, 8)
    tb.write(0x048, 4)
    tb.write(0x04C, 1)             # start
    tb.delay(20)
    tb.read_check(0x020, 0xAA)     # scratch[8]
    tb.read_check(0x024, 0xBB)     # scratch[9]
    tb.read_check(0x028, 0xCC)
    tb.read_check(0x02C, 0xDD)
    tb.read_check(0x054, 1)        # transfers count

    for i in range(16):
        tb.write(i * 4, i * 0x11)
    tb.read_check(0x000, 0x00)
    tb.read_check(0x03C, 0xFF)
    tb.write(0x04C, 2)
    tb.write(0x040, 0)
    tb.write(0x044, 8)
    tb.write(0x048, 4)
    tb.write(0x04C, 1)
    tb.delay(20)
    tb.read_check(0x020, 0x00)
    tb.read_check(0x024, 0x11)
    tb.read_check(0x028, 0x22)
    tb.read_check(0x02C, 0x33)
    tb.adversarial_write(0x050, 0)
    tb.adversarial_write(0x054, 0)
    tb.read_mix(0x054, None)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"FERRY torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
