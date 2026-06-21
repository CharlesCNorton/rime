#!/usr/bin/env python3
"""GLYPH compositor test: RIME-I + GF(2^8) arithmetic unit.

Tests:
  1. GF multiply: 0x53 * 0xCA = 0x01 (known AES test vector)
  2. GF multiply identity: A * 1 = A for several values
  3. GF inverse: inv(0x53) then verify inv * 0x53 = 1 via EXP+MUL
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

G_A    = MOD_BASE + 0x000
G_B    = MOD_BASE + 0x004
G_MUL  = MOD_BASE + 0x008
G_INV  = MOD_BASE + 0x00C  # same as EXP result after inv
G_EXP  = MOD_BASE + 0x010
G_CTRL = MOD_BASE + 0x014
G_STAT = MOD_BASE + 0x018


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

    # --- Test 1: 0x53 * 0xCA = 0x01 (AES MixColumns identity) ---
    asm.li(t0, G_A)
    asm.addi(t1, x0, 0x53)
    asm.sw(t1, t0, 0)
    asm.li(t0, G_B)
    asm.li(t1, 0xCA)
    asm.sw(t1, t0, 0)
    asm.li(t0, G_MUL)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 1)
    asm.bne(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: A * 1 = A for A = 0x37, 0xFF, 0x01 ---
    asm.label("test2")
    asm.addi(s2, x0, 0)  # errors

    # 0x37 * 1
    asm.li(t0, G_A)
    asm.addi(t1, x0, 0x37)
    asm.sw(t1, t0, 0)
    asm.li(t0, G_B)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, G_MUL)
    asm.lw(s0, t0, 0)
    asm.addi(t0, x0, 0x37)
    asm.bne(s0, t0, "t2e1")
    asm.j("t2c2")
    asm.label("t2e1")
    asm.addi(s2, s2, 1)

    # 0xFF * 1
    asm.label("t2c2")
    asm.li(t0, G_A)
    asm.addi(t1, x0, 0xFF)
    asm.sw(t1, t0, 0)
    asm.li(t0, G_MUL)
    asm.lw(s0, t0, 0)
    asm.addi(t0, x0, 0xFF)
    asm.bne(s0, t0, "t2e2")
    asm.j("t2c3")
    asm.label("t2e2")
    asm.addi(s2, s2, 1)

    # 0x01 * 1
    asm.label("t2c3")
    asm.li(t0, G_A)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, G_MUL)
    asm.lw(s0, t0, 0)
    asm.addi(t0, x0, 1)
    asm.bne(s0, t0, "t2e3")
    asm.j("t2chk")
    asm.label("t2e3")
    asm.addi(s2, s2, 1)

    asm.label("t2chk")
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.bne(s2, x0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: inverse of 0x53, verify inv * 0x53 = 1 ---
    asm.label("test3")
    asm.li(t0, G_A)
    asm.addi(t1, x0, 0x53)
    asm.sw(t1, t0, 0)
    # Trigger inverse (A^254)
    asm.li(t0, G_CTRL)
    asm.addi(t1, x0, 2)   # bit 1 = start INV
    asm.sw(t1, t0, 0)
    # Wait for done
    asm.li(t0, G_STAT)
    asm.label("iwait")
    asm.lw(t1, t0, 0)
    asm.beq(t1, x0, "iwait")
    # Read inverse
    asm.li(t0, G_INV)
    asm.lw(s0, t0, 0)     # s0 = inv(0x53)

    # Now multiply inv * 0x53, should get 1
    asm.li(t0, G_A)
    asm.sw(s0, t0, 0)     # A = inv
    asm.li(t0, G_B)
    asm.addi(t1, x0, 0x53)
    asm.sw(t1, t0, 0)     # B = 0x53
    asm.li(t0, G_MUL)
    asm.lw(s1, t0, 0)     # s1 = inv * 0x53

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 1)
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
    ok = run_module_test("glyph", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
