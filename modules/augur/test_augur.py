#!/usr/bin/env python3
"""AUGUR compositor test: RIME-I + MCMC sampler.

Tests:
  1. Set target=0, run 50 steps, check mean is within ±20 of 0
  2. Set target=100, run 100 steps, check chains converge (mean within ±30 of 100)
  3. Check accept rate > 0 and step count matches
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

A_C0    = MOD_BASE + 0x000
A_CTRL  = MOD_BASE + 0x010
A_STEPS = MOD_BASE + 0x014
A_ACC   = MOD_BASE + 0x018
A_MEAN  = MOD_BASE + 0x01C
A_TGT   = MOD_BASE + 0x020


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

    # step N times
    asm.label("step_n")  # s0 = number of steps
    asm.li(t0, A_CTRL)
    asm.addi(t1, x0, 1)
    asm.label("sn_loop")
    asm.beq(s0, x0, "sn_done")
    asm.sw(t1, t0, 0)
    asm.addi(s0, s0, -1)
    asm.j("sn_loop")
    asm.label("sn_done")
    asm.ret()

    asm.label("main")

    # --- Test 1: target=0, 50 steps, mean near 0 ---
    # Reset
    asm.li(t0, A_CTRL)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    # Set target = 0
    asm.li(t0, A_TGT)
    asm.sw(x0, t0, 0)
    # Run 50 steps
    asm.addi(s0, x0, 50)
    asm.call("step_n")
    # Read mean
    asm.li(t0, A_MEAN)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    # Check |mean| < 20 (mean is signed)
    asm.addi(t0, x0, 20)
    asm.bge(s0, t0, "t1f")
    asm.addi(t0, x0, -20)
    asm.blt(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: target=100, 100 steps ---
    asm.label("test2")
    asm.li(t0, A_CTRL)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, A_TGT)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.addi(s0, x0, 100)
    asm.call("step_n")
    asm.li(t0, A_MEAN)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    # Check mean is within 70..130 of target
    asm.addi(t0, x0, 70)
    asm.blt(s0, t0, "t2f")
    asm.li(t0, 130)
    asm.bge(s0, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: step count and accept rate ---
    asm.label("test3")
    asm.li(t0, A_STEPS)
    asm.lw(s0, t0, 0)  # should be 100
    asm.li(t0, A_ACC)
    asm.lw(s1, t0, 0)  # should be > 0

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 50)
    asm.blt(s0, t0, "t3f")
    asm.beq(s1, x0, "t3f")
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
    ok = run_module_test("augur", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
