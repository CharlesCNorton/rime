#!/usr/bin/env python3
"""CAIRN compositor test: RIME-I + stack machine coprocessor.

Tests:
  1. PUSH 3, PUSH 4, ADD, POP → 7
  2. PUSH 10, PUSH 3, SUB, POP → 7
  PUSH 5, DUP, MUL, POP → 25
  3. PUSH 100, PUSH 100, EQ → 1
  PUSH 50, PUSH 100, LT → 1
  verify depth
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

C_PUSH  = MOD_BASE + 0x000
C_POP   = MOD_BASE + 0x004
C_PEEK  = MOD_BASE + 0x008
C_OP    = MOD_BASE + 0x00C
C_DEPTH = MOD_BASE + 0x010
C_CTRL  = MOD_BASE + 0x014

# Op codes
OP_DUP=1
OP_SWAP=2
OP_DROP=3
OP_ADD=4
OP_SUB=5
OP_MUL=6
OP_AND=7
OP_OR=8
OP_XOR=9
OP_NOT=10
OP_LT=11
OP_EQ=12


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

    def push(val):
        asm.li(t0, C_PUSH)
        asm.li(t1, val)
        asm.sw(t1, t0, 0)

    def op(code):
        asm.li(t0, C_OP)
        asm.addi(t1, x0, code)
        asm.sw(t1, t0, 0)

    def pop_into(reg):
        asm.li(t0, C_POP)
        asm.lw(reg, t0, 0)

    def clear():
        asm.li(t0, C_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: 3 + 4 = 7 ---
    clear()
    push(3)
    push(4)
    op(OP_ADD)
    pop_into(s0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 7)
    asm.bne(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: 10-3=7, 5*5=25 ---
    asm.label("test2")
    clear()
    push(10)
    push(3)
    op(OP_SUB)
    pop_into(s0)  # should be 7

    clear()
    push(5)
    op(OP_DUP)
    op(OP_MUL)
    pop_into(s1)  # should be 25

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 7)
    asm.bne(s0, t0, "t2f")
    asm.addi(t0, x0, 25)
    asm.bne(s1, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: EQ, LT, depth ---
    asm.label("test3")
    clear()
    push(100)
    push(100)
    op(OP_EQ)
    pop_into(s0)  # should be 1

    push(50)
    push(100)
    op(OP_LT)
    pop_into(s1)  # should be 1

    # Check depth = 0 (all popped)
    asm.li(t0, C_DEPTH)
    asm.lw(s2, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 1)
    asm.bne(s0, t0, "t3f")
    asm.bne(s1, t0, "t3f")
    asm.bne(s2, x0, "t3f")
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
    ok = run_module_test("cairn", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
