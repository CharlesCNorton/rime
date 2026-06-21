#!/usr/bin/env python3
"""WEAVE compositor test: RIME-I + bit-serial ALU.

Tests:
  1. Add: 100 + 200 = 300
  2. Sub: 500 - 123 = 377
  3. Mul: 7 * 13 = 91
  XOR: 0xAA ^ 0x55 = 0xFF
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, t3, a0, s0, s1, s2, s3, s4, MOD_BASE

W_A    = MOD_BASE + 0x000
W_B    = MOD_BASE + 0x004
W_CMD  = MOD_BASE + 0x008
W_RES  = MOD_BASE + 0x00C
W_STAT = MOD_BASE + 0x010

CMD_ADD=0
CMD_SUB=1
CMD_MUL=2
CMD_AND=3
CMD_OR=4
CMD_XOR=5


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

    # compute: set A=s0, B=s1, CMD=s2, wait, result in s3
    asm.label("compute")
    asm.li(t0, W_A)
    asm.sw(s0, t0, 0)
    asm.li(t0, W_B)
    asm.sw(s1, t0, 0)
    asm.li(t0, W_CMD)
    asm.sw(s2, t0, 0)
    asm.li(t0, W_STAT)
    asm.label("cwait")
    asm.lw(t1, t0, 0)
    asm.andi(t1, t1, 1)  # done bit
    asm.beq(t1, x0, "cwait")
    asm.li(t0, W_RES)
    asm.lw(s3, t0, 0)
    asm.ret()

    asm.label("main")

    # --- Test 1: 100 + 200 = 300 ---
    asm.addi(s0, x0, 100)
    asm.addi(s1, x0, 200)
    asm.addi(s2, x0, CMD_ADD)
    asm.call("compute")

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.li(t0, 300)
    asm.bne(s3, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: 500 - 123 = 377 ---
    asm.label("test2")
    asm.li(s0, 500)
    asm.addi(s1, x0, 123)
    asm.addi(s2, x0, CMD_SUB)
    asm.call("compute")

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.li(t0, 377)
    asm.bne(s3, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: 7*13=91, 0xAA^0x55=0xFF ---
    asm.label("test3")
    asm.addi(s0, x0, 7)
    asm.addi(s1, x0, 13)
    asm.addi(s2, x0, CMD_MUL)
    asm.call("compute")
    # s3 = 91?

    asm.addi(t3, x0, 0)  # errors
    asm.addi(t0, x0, 91)
    asm.beq(s3, t0, "t3_xor")
    asm.addi(t3, t3, 1)

    asm.label("t3_xor")
    asm.li(s0, 0xAA)
    asm.addi(s1, x0, 0x55)
    asm.addi(s2, x0, CMD_XOR)
    asm.call("compute")
    asm.addi(t0, x0, 0xFF)
    asm.beq(s3, t0, "t3chk")
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
    ok = run_module_test("weave", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
