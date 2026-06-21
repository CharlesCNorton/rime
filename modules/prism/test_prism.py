#!/usr/bin/env python3
"""PRISM compositor test: RIME-I + color space converter.

Tests:
  1. White (255,255,255) → luma=255, sat=0
  2. Pure red (255,0,0) → luma≈77, sat=255
  3. Gray (128,128,128) → luma≈128, invert=(127,127,127)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

P_RGB  = MOD_BASE + 0x000
P_LUMA = MOD_BASE + 0x004
P_MIN  = MOD_BASE + 0x008
P_MAX  = MOD_BASE + 0x00C
P_SAT  = MOD_BASE + 0x010
P_INV  = MOD_BASE + 0x014


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

    def set_rgb(r, g, b):
        asm.li(t0, P_RGB)
        asm.li(t1, (r << 16) | (g << 8) | b)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: white → luma=255, sat=0 ---
    set_rgb(255, 255, 255)
    asm.li(t0, P_LUMA)
    asm.lw(s0, t0, 0)
    asm.li(t0, P_SAT)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    # luma should be ~255 (might be 254 due to rounding)
    asm.addi(t0, x0, 250)
    asm.blt(s0, t0, "t1f")
    asm.bne(s1, x0, "t1f")  # sat should be 0
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: red → luma≈77, sat=255 ---
    asm.label("test2")
    set_rgb(255, 0, 0)
    asm.li(t0, P_LUMA)
    asm.lw(s0, t0, 0)
    asm.li(t0, P_SAT)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 70)
    asm.blt(s0, t0, "t2f")
    asm.addi(t0, x0, 85)
    asm.bge(s0, t0, "t2f")
    asm.addi(t0, x0, 255)
    asm.bne(s1, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: gray(128) → luma≈128, invert has 127 ---
    asm.label("test3")
    set_rgb(128, 128, 128)
    asm.li(t0, P_LUMA)
    asm.lw(s0, t0, 0)
    asm.li(t0, P_INV)
    asm.lw(s1, t0, 0)  # should be (127,127,127) = 0x007F7F7F

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 124)
    asm.blt(s0, t0, "t3f")
    asm.addi(t0, x0, 132)
    asm.bge(s0, t0, "t3f")
    asm.li(t0, 0x007F7F7F)
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
    ok = run_module_test("prism", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
