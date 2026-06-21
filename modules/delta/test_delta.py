#!/usr/bin/env python3
"""DELTA compositor test: RIME-I + XOR differencing engine.

Tests:
  1. Compare identical bytes: old=0x42, new=0x42 → diff=0, changed=0, same=1
  2. Compare different bytes: old=0xFF, new=0x00 → diff=0xFF, changed=1
  3. Compare 10-byte streams with 3 differences, verify counters
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

D_OLD  = MOD_BASE + 0x000
D_NEW  = MOD_BASE + 0x004
D_DIFF = MOD_BASE + 0x008
D_CHG  = MOD_BASE + 0x00C
D_TOT  = MOD_BASE + 0x010
D_CTRL = MOD_BASE + 0x014
D_SAME = MOD_BASE + 0x018


def gen_firmware():
    asm = RV32I()
    asm.lui(sp, 0x00001)
    asm.lui(s4, 0x20000)
    asm.j("main")

    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    def reset():
        asm.li(t0, D_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    def compare(old_val, new_val):
        asm.li(t0, D_OLD)
        asm.addi(t1, x0, old_val)
        asm.sw(t1, t0, 0)
        asm.li(t0, D_NEW)
        asm.addi(t1, x0, new_val)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: identical ---
    reset()
    compare(0x42, 0x42)

    asm.li(t0, D_DIFF)
    asm.lw(s0, t0, 0)  # 0
    asm.li(t0, D_SAME)
    asm.lw(s1, t0, 0)  # 1

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.bne(s0, x0, "t1f")
    asm.addi(t0, x0, 1)
    asm.bne(s1, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: different ---
    asm.label("test2")
    reset()
    compare(0xFF, 0x00)

    asm.li(t0, D_DIFF)
    asm.lw(s0, t0, 0)  # 0xFF
    asm.li(t0, D_CHG)
    asm.lw(s1, t0, 0)  # 1

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 0xFF)
    asm.bne(s0, t0, "t2f")
    asm.addi(t0, x0, 1)
    asm.bne(s1, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: 10 bytes, 3 different ---
    asm.label("test3")
    reset()
    # Same: 0-6 (7 bytes)
    for i in range(7):
        compare(0x41 + i, 0x41 + i)
    # Different: 7-9 (3 bytes)
    compare(0x10, 0x20)
    compare(0x30, 0x40)
    compare(0x50, 0x60)

    asm.li(t0, D_TOT)
    asm.lw(s0, t0, 0)  # 10
    asm.li(t0, D_CHG)
    asm.lw(s1, t0, 0)  # 3
    asm.li(t0, D_SAME)
    asm.lw(s2, t0, 0)  # 7

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 10)
    asm.bne(s0, t0, "t3f")
    asm.addi(t0, x0, 3)
    asm.bne(s1, t0, "t3f")
    asm.addi(t0, x0, 7)
    asm.bne(s2, t0, "t3f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("done")
    asm.label("t3f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    asm.label("done")
    asm.addi(a0, x0, 10)
    asm.call("putc")
    asm.li(t0, 0x200000)
    asm.label("delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "delay")
    asm.j("main")

    asm.resolve()
    return asm.code


def main():
    firmware = gen_firmware()
    ok = run_module_test("delta", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
