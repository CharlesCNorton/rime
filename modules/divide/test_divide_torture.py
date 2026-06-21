#!/usr/bin/env python3
"""DIVIDE hash-based torture test.

Threads a running hash through every DIVIDE operation: basic division,
division by 1, division by self, division by power of 2, large quotient,
large remainder, division by zero, reset, rapid re-trigger.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

DIVIDEND = 0x000
DIVISOR  = 0x004
QUOTIENT = 0x008
REMAIN   = 0x00C
STATUS   = 0x010
CONTROL  = 0x014


def gen():
    tb = TortureBuilder("divide")

    tb.reset(CONTROL, bit=0)

    # --- Basic: 100 / 7 = 14 remainder 2 ---
    tb.write(DIVIDEND, 100)
    tb.write(DIVISOR, 7)
    tb.delay(40)
    tb.read_check(STATUS, 0x01)
    tb.read_check(QUOTIENT, 14)
    tb.read_check(REMAIN, 2)

    # --- Division by 1: N / 1 = N remainder 0 ---
    tb.write(DIVIDEND, 0xDEADBEEF)
    tb.write(DIVISOR, 1)
    tb.delay(40)
    tb.read_check(QUOTIENT, 0xDEADBEEF)
    tb.read_check(REMAIN, 0)

    # --- Division by self: N / N = 1 remainder 0 ---
    tb.write(DIVIDEND, 12345)
    tb.write(DIVISOR, 12345)
    tb.delay(40)
    tb.read_check(QUOTIENT, 1)
    tb.read_check(REMAIN, 0)

    # --- Large quotient: 0xFFFFFFFF / 1 ---
    tb.write(DIVIDEND, 0xFFFFFFFF)
    tb.write(DIVISOR, 1)
    tb.delay(40)
    tb.read_check(QUOTIENT, 0xFFFFFFFF)
    tb.read_check(REMAIN, 0)

    # --- Large remainder: 1 / 0xFFFFFFFF = 0 remainder 1 ---
    tb.write(DIVIDEND, 1)
    tb.write(DIVISOR, 0xFFFFFFFF)
    tb.delay(40)
    tb.read_check(QUOTIENT, 0)
    tb.read_check(REMAIN, 1)

    # --- Power of 2: 0x80000000 / 0x10000 = 0x8000 ---
    tb.write(DIVIDEND, 0x80000000)
    tb.write(DIVISOR, 0x10000)
    tb.delay(40)
    tb.read_check(QUOTIENT, 0x8000)
    tb.read_check(REMAIN, 0)

    # --- Division by zero: should produce 0xFFFFFFFF quotient, dividend as remainder ---
    tb.write(DIVIDEND, 42)
    tb.write(DIVISOR, 0)
    tb.read_check(STATUS, 0x03)
    tb.read_check(QUOTIENT, 0xFFFFFFFF)
    tb.read_check(REMAIN, 42)

    # --- Reset and verify clean ---
    tb.reset(CONTROL, bit=0)
    tb.read_check(STATUS, 0x00)
    tb.read_check(QUOTIENT, 0)
    tb.read_check(REMAIN, 0)

    # --- Adversarial: rapid re-trigger (write new divisor before done) ---
    tb.write(DIVIDEND, 1000000)
    tb.write(DIVISOR, 3)
    tb.write(DIVISOR, 7)
    tb.delay(40)
    tb.read_check(QUOTIENT, 1000000 // 7)
    tb.read_check(REMAIN, 1000000 % 7)

    # --- 0 / N = 0 remainder 0 ---
    tb.write(DIVIDEND, 0)
    tb.write(DIVISOR, 999)
    tb.delay(40)
    tb.read_check(QUOTIENT, 0)
    tb.read_check(REMAIN, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"DIVIDE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("divide", firmware, mod_dir / "top.sv")
    ok, luts = build_module("divide", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("divide")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
