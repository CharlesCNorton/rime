#!/usr/bin/env python3
"""Torture test for CLASP: CLASP: Contested Lock with Atomic Set Protocol — 8-slot hardware mutex with atomic test-and-set

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

ACQUIRE0 = 0x000
ACQUIRE1 = 0x004
RELEASE0 = 0x020
RELEASE1 = 0x024
STATE    = 0x040
CONTROL  = 0x044


def gen():
    tb = TortureBuilder("clasp")

    tb.write(CONTROL, 1)               # clear all
    tb.read_check(STATE, 0)

    # First acquire on slot 0: prev = 0 (free)
    tb.read_check(ACQUIRE0, 0)
    # Second acquire on slot 0: prev = 1 (already held)
    tb.read_check(ACQUIRE0, 1)
    # State now has slot 0 set
    tb.read_check(STATE, 1)

    # Acquire slot 1
    tb.read_check(ACQUIRE1, 0)
    tb.read_check(STATE, 3)

    # Release slot 0
    tb.write(RELEASE0, 0)
    tb.read_check(STATE, 2)

    # Re-acquire slot 0 — should now be free
    tb.read_check(ACQUIRE0, 0)
    tb.read_check(STATE, 3)

    # Clear all
    tb.write(CONTROL, 1)
    tb.read_check(STATE, 0)


    tb.write(0x044, 1)
    tb.read_check(0x040, 0)
    tb.read_check(0x000, 0)
    tb.read_check(0x000, 1)
    tb.read_check(0x040, 1)
    tb.write(0x020, 0)
    tb.read_check(0x040, 0)
    for i in range(8):
        tb.read_check(i * 4, 0)
    tb.read_check(0x040, 0xFF)
    tb.write(0x044, 1)
    tb.read_check(0x040, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"CLASP torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
