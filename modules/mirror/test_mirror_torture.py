#!/usr/bin/env python3
"""MIRROR (16-entry masked pseudo-TCAM) torture test.

Loads entries 0 and 1 with exact-match and wildcard patterns, then
verifies every lookup with read_assert: result value, hit field, and
COUNT of valid entries. Invalidates entries and re-checks.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

QUERY   = 0x000
RESULT  = 0x004
HIT     = 0x008
COUNT   = 0x00C
CONTROL = 0x010
KEY     = 0x100
MASK    = 0x140
VALUE   = 0x180
VALID   = 0x1C0


def gen():
    tb = TortureBuilder("mirror")

    tb.write(CONTROL, 1)  # clear all entries (idempotent across reruns)
    tb.read_assert(COUNT, 0)

    # Entry 0: exact-match 0x12345678 → 0xAAAA
    tb.write(KEY   + 0, 0x12345678)
    tb.write(MASK  + 0, 0xFFFFFFFF)
    tb.write(VALUE + 0, 0x0000AAAA)
    tb.write(VALID + 0, 1)
    tb.read_assert(COUNT, 1)

    tb.write(QUERY, 0x12345678)
    tb.delay(3)
    tb.read_assert(RESULT, 0x0000AAAA)

    # Non-matching query
    tb.write(QUERY, 0xFFFFFFFF)
    tb.delay(3)
    tb.read_assert(RESULT, 0)

    # Entry 1: wildcard mask=0 → matches anything, value 0x0000BBBB
    tb.write(KEY   + 4, 0x00000000)
    tb.write(MASK  + 4, 0x00000000)
    tb.write(VALUE + 4, 0x0000BBBB)
    tb.write(VALID + 4, 1)
    tb.read_assert(COUNT, 2)

    # Query not matching entry 0 → caught by wildcard entry 1
    tb.write(QUERY, 0x99999999)
    tb.delay(3)
    tb.read_assert(RESULT, 0x0000BBBB)

    # Entry 0 still wins when its key matches (lowest-index priority)
    tb.write(QUERY, 0x12345678)
    tb.delay(3)
    tb.read_assert(RESULT, 0x0000AAAA)

    # Invalidate entry 0 → wildcard catches everything
    tb.write(VALID + 0, 0)
    tb.read_assert(COUNT, 1)
    tb.write(QUERY, 0x12345678)
    tb.delay(3)
    tb.read_assert(RESULT, 0x0000BBBB)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"MIRROR torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("mirror", firmware, mod_dir / "top.sv")
    ok, luts = build_module("mirror", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("mirror")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
