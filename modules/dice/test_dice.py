#!/usr/bin/env python3
"""DICE compositor test: RIME-I + stochastic computing matrix.

Tests:
  1. Multiply 128*128 (0.5*0.5=0.25), result should be ~64 (±16)
  2. Add 64+192 ((0.25+0.75)/2=0.5), result should be ~128 (±20)
  3. Multiply sequence: 0*X=0, 255*X≈X, 128*128≈64, verify all within tolerance
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, t3, a0, s0, s1, s2, s3, s4, MOD_BASE

DICE_A    = MOD_BASE + 0x000
DICE_B    = MOD_BASE + 0x004
DICE_MUL  = MOD_BASE + 0x008
DICE_CTRL = MOD_BASE + 0x00C
DICE_STAT = MOD_BASE + 0x010
DICE_ADD  = MOD_BASE + 0x014


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

    # compute: set A, B, trigger, wait, return MUL result in s0, ADD in s1
    asm.label("compute")
    # a0=opA, a1=opB (caller sets them before call)
    # But we can't use a0/a1 as both args and putc arg. Use s-regs.
    # Actually, let's use t-regs for args
    asm.li(t0, DICE_A)
    asm.sw(s0, t0, 0)         # A = s0
    asm.li(t0, DICE_B)
    asm.sw(s1, t0, 0)         # B = s1
    asm.li(t0, DICE_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)         # start
    asm.li(t0, DICE_STAT)
    asm.label("cwait")
    asm.lw(t1, t0, 0)
    asm.beq(t1, x0, "cwait")
    asm.li(t0, DICE_MUL)
    asm.lw(s2, t0, 0)         # s2 = mul result
    asm.li(t0, DICE_ADD)
    asm.lw(s3, t0, 0)         # s3 = add result
    asm.ret()

    asm.label("main")

    # --- Test 1: 128*128 ≈ 64 (±16) ---
    asm.addi(s0, x0, 128)
    asm.addi(s1, x0, 128)
    asm.call("compute")
    # s2 = mul result, should be 48-80
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 48)
    asm.blt(s2, t0, "t1f")
    asm.addi(t0, x0, 80)
    asm.bge(s2, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: add 64+192 ≈ 128 (±20) ---
    asm.label("test2")
    asm.addi(s0, x0, 64)
    asm.addi(s1, x0, 192)
    asm.call("compute")
    # s3 = add result, should be 108-148
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 108)
    asm.blt(s3, t0, "t2f")
    asm.addi(t0, x0, 148)
    asm.bge(s3, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: 0*128=0, 255*128≈128, 128*128≈64 ---
    asm.label("test3")
    asm.addi(s0, x0, 0)
    asm.addi(s1, x0, 128)
    asm.call("compute")
    # s2 should be 0 (or very close, <5)
    asm.addi(t3, x0, 0)       # error count

    asm.addi(t0, x0, 5)
    asm.bge(s2, t0, "t3e1")
    asm.j("t3c2")
    asm.label("t3e1")
    asm.addi(t3, t3, 1)

    asm.label("t3c2")
    asm.addi(s0, x0, 255)
    asm.addi(s1, x0, 128)
    asm.call("compute")
    # s2 should be ~128 (108-148)
    asm.addi(t0, x0, 108)
    asm.blt(s2, t0, "t3e2")
    asm.addi(t0, x0, 148)
    asm.bge(s2, t0, "t3e2")
    asm.j("t3c3")
    asm.label("t3e2")
    asm.addi(t3, t3, 1)

    asm.label("t3c3")
    asm.addi(s0, x0, 128)
    asm.addi(s1, x0, 128)
    asm.call("compute")
    # s2 should be ~64 (48-80)
    asm.addi(t0, x0, 48)
    asm.blt(s2, t0, "t3e3")
    asm.addi(t0, x0, 80)
    asm.bge(s2, t0, "t3e3")
    asm.j("t3chk")
    asm.label("t3e3")
    asm.addi(t3, t3, 1)

    asm.label("t3chk")
    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(t3, x0, "t3f")
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
    ok = run_module_test("dice", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
