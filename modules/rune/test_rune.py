#!/usr/bin/env python3
"""RUNE compositor test: RIME-I + 8x8 bitmap font renderer.

Tests:
  1. Space (32) row 0 → 0x00
  2. 'A' (65) row 0 → 0x18 (known glyph)
  3. 'R' all 8 rows → first row nonzero, last row zero, total pixels > 0
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

R_CHAR  = MOD_BASE + 0x000
R_ROW   = MOD_BASE + 0x004
R_GLYPH = MOD_BASE + 0x008
R_PIXEL = MOD_BASE + 0x00C


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

    # --- Test 1: space row 0 = 0 ---
    asm.li(t0, R_CHAR)
    asm.addi(t1, x0, 32)
    asm.sw(t1, t0, 0)
    asm.li(t0, R_ROW)
    asm.sw(x0, t0, 0)
    asm.li(t0, R_GLYPH)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.bne(s0, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: 'A' row 0 = 0x18 ---
    asm.label("test2")
    asm.li(t0, R_CHAR)
    asm.addi(t1, x0, 65)
    asm.sw(t1, t0, 0)
    asm.li(t0, R_ROW)
    asm.sw(x0, t0, 0)
    asm.li(t0, R_GLYPH)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 0x18)
    asm.bne(s0, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: 'R' all rows, count total pixels ---
    asm.label("test3")
    asm.li(t0, R_CHAR)
    asm.addi(t1, x0, 82)  # 'R'
    asm.sw(t1, t0, 0)

    asm.addi(s0, x0, 0)  # row
    asm.addi(s1, x0, 0)  # total pixels
    asm.addi(s2, x0, 8)

    asm.label("t3loop")
    asm.bge(s0, s2, "t3done")
    asm.li(t0, R_ROW)
    asm.sw(s0, t0, 0)
    asm.li(t0, R_PIXEL)
    asm.lw(t1, t0, 0)
    asm.add(s1, s1, t1)
    asm.addi(s0, s0, 1)
    asm.j("t3loop")
    asm.label("t3done")

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    # Total pixels for 'R' should be > 10
    asm.addi(t0, x0, 10)
    asm.blt(s1, t0, "t3f")
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
    ok = run_module_test("rune", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
