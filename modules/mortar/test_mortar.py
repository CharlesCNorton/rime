#!/usr/bin/env python3
"""MORTAR compositor test: RIME-I + 2x2 matrix multiply.

Tests:
  1. Identity * A = A: [[1,0],[0,1]] * [[3,4],[5,6]] = [[3,4],[5,6]]
  2. Scale: [[2,0],[0,2]] * [[3,4],[5,6]] = [[6,8],[10,12]]
  3. General: [[1,2],[3,4]] * [[5,6],[7,8]] = [[19,22],[43,50]]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

M_A00 = MOD_BASE + 0x000
M_B00 = MOD_BASE + 0x010
M_C00 = MOD_BASE + 0x020


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

    def set_a(a00, a01, a10, a11):
        for i, v in enumerate([a00, a01, a10, a11]):
            asm.li(t0, M_A00 + i * 4)
            asm.addi(t1, x0, v)
            asm.sw(t1, t0, 0)

    def set_b(b00, b01, b10, b11):
        for i, v in enumerate([b00, b01, b10, b11]):
            asm.li(t0, M_B00 + i * 4)
            asm.addi(t1, x0, v)
            asm.sw(t1, t0, 0)

    def read_c(c00_reg, c01_reg):
        asm.li(t0, M_C00)
        asm.lw(c00_reg, t0, 0)
        asm.lw(c01_reg, t0, 4)

    asm.label("main")

    # --- Test 1: Identity * [[3,4],[5,6]] = [[3,4],[5,6]] ---
    set_a(1, 0, 0, 1)
    set_b(3, 4, 5, 6)
    read_c(s0, s1)  # c00=3, c01=4

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 3)
    asm.bne(s0, t0, "t1f")
    asm.addi(t0, x0, 4)
    asm.bne(s1, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: [[2,0],[0,2]] * [[3,4],[5,6]] = [[6,8],[10,12]] ---
    asm.label("test2")
    set_a(2, 0, 0, 2)
    set_b(3, 4, 5, 6)
    read_c(s0, s1)  # c00=6, c01=8

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 6)
    asm.bne(s0, t0, "t2f")
    asm.addi(t0, x0, 8)
    asm.bne(s1, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: [[1,2],[3,4]] * [[5,6],[7,8]] = [[19,22],[43,50]] ---
    asm.label("test3")
    set_a(1, 2, 3, 4)
    set_b(5, 6, 7, 8)
    read_c(s0, s1)  # c00=19, c01=22

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 19)
    asm.bne(s0, t0, "t3f")
    asm.addi(t0, x0, 22)
    asm.bne(s1, t0, "t3f")
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
    ok = run_module_test("mortar", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
