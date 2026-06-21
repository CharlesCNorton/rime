#!/usr/bin/env python3
"""CRANK hash-based torture test.

Threads a running hash through every CRANK operation: basic multiply,
multiply by 0, multiply by 1, full-range 64-bit product, power-of-2
operands, reset, rapid re-trigger.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

OP_A      = 0x000
OP_B      = 0x004
RESULT_LO = 0x008
RESULT_HI = 0x00C
STATUS    = 0x010
CONTROL   = 0x014


def gen():
    tb = TortureBuilder("crank")

    tb.reset(CONTROL, bit=0)

    # --- Basic: 7 * 13 = 91 ---
    tb.write(OP_A, 7)
    tb.write(OP_B, 13)
    tb.delay(40)
    tb.read_check(STATUS, 0x01)
    tb.read_check(RESULT_LO, 91)
    tb.read_check(RESULT_HI, 0)

    # --- Multiply by 0 ---
    tb.write(OP_A, 0xDEADBEEF)
    tb.write(OP_B, 0)
    tb.delay(40)
    tb.read_check(RESULT_LO, 0)
    tb.read_check(RESULT_HI, 0)

    # --- Multiply by 1 ---
    tb.write(OP_A, 0xCAFEBABE)
    tb.write(OP_B, 1)
    tb.delay(40)
    tb.read_check(RESULT_LO, 0xCAFEBABE)
    tb.read_check(RESULT_HI, 0)

    # --- Full 64-bit: 0xDEADBEEF * 0xCAFEBABE ---
    a_val = 0xDEADBEEF
    b_val = 0xCAFEBABE
    product = a_val * b_val
    lo = product & 0xFFFFFFFF
    hi = (product >> 32) & 0xFFFFFFFF
    tb.write(OP_A, a_val)
    tb.write(OP_B, b_val)
    tb.delay(40)
    tb.read_check(RESULT_LO, lo)
    tb.read_check(RESULT_HI, hi)

    # --- Power of 2: 0x80000000 * 2 ---
    product2 = 0x80000000 * 2
    tb.write(OP_A, 0x80000000)
    tb.write(OP_B, 2)
    tb.delay(40)
    tb.read_check(RESULT_LO, product2 & 0xFFFFFFFF)
    tb.read_check(RESULT_HI, (product2 >> 32) & 0xFFFFFFFF)

    # --- Max * Max: 0xFFFFFFFF * 0xFFFFFFFF ---
    product3 = 0xFFFFFFFF * 0xFFFFFFFF
    tb.write(OP_A, 0xFFFFFFFF)
    tb.write(OP_B, 0xFFFFFFFF)
    tb.delay(40)
    tb.read_check(RESULT_LO, product3 & 0xFFFFFFFF)
    tb.read_check(RESULT_HI, (product3 >> 32) & 0xFFFFFFFF)

    # --- Reset and verify clean ---
    tb.reset(CONTROL, bit=0)
    tb.read_check(STATUS, 0x00)
    tb.read_check(RESULT_LO, 0)
    tb.read_check(RESULT_HI, 0)

    # --- Adversarial: rapid re-trigger ---
    tb.write(OP_A, 100)
    tb.write(OP_B, 3)
    tb.write(OP_B, 5)
    tb.delay(40)
    tb.read_check(RESULT_LO, 500)
    tb.read_check(RESULT_HI, 0)

    # --- 1 * 1 ---
    tb.write(OP_A, 1)
    tb.write(OP_B, 1)
    tb.delay(40)
    tb.read_check(RESULT_LO, 1)
    tb.read_check(RESULT_HI, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"CRANK torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("crank", firmware, mod_dir / "top.sv")
    ok, luts = build_module("crank", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("crank")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
