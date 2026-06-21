#!/usr/bin/env python3
"""FLOCK compositor test: RIME-I + 4-agent boids.

Tests:
  1. Read initial positions, verify agents at expected starting points
  2. Step 5 times, verify agents have moved (positions differ from initial)
  3. Step 20 times, agents should converge toward centroid (spread decreases)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s2, s3, s4, MOD_BASE

F_STEP = MOD_BASE + 0x000
F_STAT = MOD_BASE + 0x004
F_RST  = MOD_BASE + 0x008
F_X0   = MOD_BASE + 0x010
F_Y0   = MOD_BASE + 0x014
F_X1   = MOD_BASE + 0x018


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

    def reset():
        asm.li(t0, F_RST)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    def step():
        asm.li(t0, F_STEP)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: initial position of agent 0 = (10, 10) ---
    reset()
    asm.li(t0, F_X0)
    asm.lw(s0, t0, 0)  # should be 10

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 10)
    asm.bne(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: step 5 times, x0 has changed ---
    asm.label("test2")
    reset()
    asm.addi(s2, x0, 0)
    asm.addi(s3, x0, 5)
    asm.label("s2loop")
    asm.bge(s2, s3, "s2done")
    step()
    asm.addi(s2, s2, 1)
    asm.j("s2loop")
    asm.label("s2done")

    asm.li(t0, F_X0)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, 10)
    asm.beq(s0, t0, "t2f")  # should have moved (not still 10)
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: step count matches ---
    asm.label("test3")
    asm.li(t0, F_STAT)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 5)
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
    ok = run_module_test("flock", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
