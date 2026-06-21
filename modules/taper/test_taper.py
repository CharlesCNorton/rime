#!/usr/bin/env python3
"""TAPER compositor test: RIME-I + saturating math coprocessor.

Tests:
  1. Add 50 + 30 = 80 (no saturation)
  2. Add 100 + 100 = 127 (saturated), multiply 10 * 5 = 50
  3. Min/Max/Abs: min(-5, 3)=-5, max(-5, 3)=3, abs(-42)=42
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

T_A   = MOD_BASE + 0x000
T_B   = MOD_BASE + 0x004
T_ADD = MOD_BASE + 0x008
T_MUL = MOD_BASE + 0x00C
T_ABS = MOD_BASE + 0x014
T_MIN = MOD_BASE + 0x018
T_MAX = MOD_BASE + 0x01C


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

    asm.label("main")

    # --- Test 1: 50 + 30 = 80 ---
    asm.li(t0, T_A)
    asm.addi(t1, x0, 50)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_B)
    asm.addi(t1, x0, 30)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_ADD)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 80)
    asm.bne(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: 100+100=127 (sat), 10*5=50 ---
    asm.label("test2")
    asm.li(t0, T_A)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_B)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_ADD)
    asm.lw(s0, t0, 0)  # should be 127

    asm.li(t0, T_A)
    asm.addi(t1, x0, 10)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_B)
    asm.addi(t1, x0, 5)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_MUL)
    asm.lw(s1, t0, 0)  # should be 50

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 127)
    asm.bne(s0, t0, "t2f")
    asm.addi(t0, x0, 50)
    asm.bne(s1, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: min(-5,3), max(-5,3), abs(-42) ---
    asm.label("test3")
    asm.li(t0, T_A)
    asm.addi(t1, x0, -5)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_B)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)

    asm.li(t0, T_MIN)
    asm.lw(s0, t0, 0)  # should be -5 = 0xFFFFFFFB
    asm.li(t0, T_MAX)
    asm.lw(s1, t0, 0)  # should be 3

    asm.li(t0, T_A)
    asm.addi(t1, x0, -42)
    asm.sw(t1, t0, 0)
    asm.li(t0, T_ABS)
    asm.lw(s2, t0, 0)  # should be 42

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, -5)
    asm.bne(s0, t0, "t3f")
    asm.addi(t0, x0, 3)
    asm.bne(s1, t0, "t3f")
    asm.addi(t0, x0, 42)
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
    ok = run_module_test("taper", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
