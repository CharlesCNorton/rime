#!/usr/bin/env python3
"""BLOOM compositor test: RIME-I + popcount/bit manipulation.

Tests:
  1. 0xFFFFFFFF → popcnt=32, parity=0
  2. 0x80000001 → clz=0, ctz=0, popcnt=2
  3. 0x12345678 → reverse=0x1E6A2C48, popcnt=13
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

B_IN   = MOD_BASE + 0x000
B_POP  = MOD_BASE + 0x004
B_CLZ  = MOD_BASE + 0x008
B_CTZ  = MOD_BASE + 0x00C
B_REV  = MOD_BASE + 0x010
B_PAR  = MOD_BASE + 0x014


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

    def set_val(v):
        asm.li(t0, B_IN)
        asm.li(t1, v)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: 0xFFFFFFFF ---
    set_val(0xFFFFFFFF)
    asm.li(t0, B_POP)
    asm.lw(s0, t0, 0)  # 32
    asm.li(t0, B_PAR)
    asm.lw(s1, t0, 0)  # 0 (even parity)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 32)
    asm.bne(s0, t0, "t1f")
    asm.bne(s1, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: 0x80000001 ---
    asm.label("test2")
    set_val(0x80000001)
    asm.li(t0, B_POP)
    asm.lw(s0, t0, 0)  # 2
    asm.li(t0, B_CLZ)
    asm.lw(s1, t0, 0)  # 0
    asm.li(t0, B_CTZ)
    asm.lw(s2, t0, 0)  # 0

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 2)
    asm.bne(s0, t0, "t2f")
    asm.bne(s1, x0, "t2f")
    asm.bne(s2, x0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: 0x12345678 → reverse, popcnt=13 ---
    asm.label("test3")
    set_val(0x12345678)
    asm.li(t0, B_POP)
    asm.lw(s0, t0, 0)  # 13
    asm.li(t0, B_REV)
    asm.lw(s1, t0, 0)  # 0x1E6A2C48

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 13)
    asm.bne(s0, t0, "t3f")
    asm.li(t0, 0x1E6A2C48)
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
    ok = run_module_test("bloom", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
