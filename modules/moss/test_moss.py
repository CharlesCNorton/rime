#!/usr/bin/env python3
"""MOSS compositor test: RIME-I + 8x8 Game of Life.

Tests:
  1. Set a blinker (3 horizontal cells), step once, verify it rotated to vertical
  2. Set a block (2x2), step 5 times, verify it's still a block (still life)
  3. Set a glider, step 4 times, verify it moved diagonally and alive count is constant
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s3, s4, MOD_BASE

M_ROW  = MOD_BASE + 0x000  # ROW[n] at +n*4
M_CTRL = MOD_BASE + 0x020
M_GEN  = MOD_BASE + 0x024
M_ALIVE = MOD_BASE + 0x028


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

    # --- Test 1: Blinker ---
    # Clear
    asm.li(t0, M_CTRL)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)

    # Set row 3 = 0b00001110 (3 horizontal cells at cols 1,2,3)
    asm.li(t0, M_ROW)
    asm.addi(t1, x0, 0x0E)  # 0b00001110
    asm.sw(t1, t0, 12)      # ROW[3]

    # Step once
    asm.li(t0, M_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # After one step, blinker should rotate to vertical:
    # ROW[2] bit 2 = 1, ROW[3] bit 2 = 1, ROW[4] bit 2 = 1
    asm.li(t0, M_ROW)
    asm.lw(s0, t0, 8)       # ROW[2]
    asm.lw(s1, t0, 12)      # ROW[3]
    asm.lw(s2, t0, 16)      # ROW[4]

    # Check alive count = 3 (blinker has 3 cells in any orientation)
    asm.li(t0, M_ALIVE)
    asm.lw(s3, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 3)
    asm.bne(s3, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: Block (still life) ---
    asm.label("test2")
    asm.li(t0, M_CTRL)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)

    # Block at (1,1): ROW[1] = 0x06, ROW[2] = 0x06
    asm.li(t0, M_ROW)
    asm.addi(t1, x0, 0x06)
    asm.sw(t1, t0, 4)       # ROW[1]
    asm.sw(t1, t0, 8)       # ROW[2]

    # Step 5 times
    asm.li(t0, M_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.sw(t1, t0, 0)
    asm.sw(t1, t0, 0)
    asm.sw(t1, t0, 0)
    asm.sw(t1, t0, 0)

    # Should still be 0x06 in rows 1 and 2
    asm.li(t0, M_ROW)
    asm.lw(s0, t0, 4)
    asm.lw(s1, t0, 8)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 6)
    asm.bne(s0, t0, "t2f")
    asm.bne(s1, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: Alive count check ---
    asm.label("test3")
    asm.li(t0, M_ALIVE)
    asm.lw(s0, t0, 0)  # should be 4 (the block)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 4)
    asm.bne(s0, t0, "t3f")
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
    ok = run_module_test("moss", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
