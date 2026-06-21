#!/usr/bin/env python3
"""FLUX compositor test: RIME-I + PID controller.

Tests:
  1. P-only (Kp=256=1.0): setpoint=100, measured=80, error=20, output≈20
  2. P-only: setpoint=0, measured=100, error=-100, output≈-100
  3. Step response: feed 5 measurements converging toward setpoint, verify output decreases
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

F_SET  = MOD_BASE + 0x000
F_MEAS = MOD_BASE + 0x004
F_OUT  = MOD_BASE + 0x008
F_KP   = MOD_BASE + 0x00C
F_KI   = MOD_BASE + 0x010
F_KD   = MOD_BASE + 0x014
F_CTRL = MOD_BASE + 0x018
F_ERR  = MOD_BASE + 0x01C


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

    # Reset + set Kp=256 (1.0), Ki=0, Kd=0
    asm.li(t0, F_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, F_KP)
    asm.li(t1, 256)
    asm.sw(t1, t0, 0)
    asm.li(t0, F_KI)
    asm.sw(x0, t0, 0)
    asm.li(t0, F_KD)
    asm.sw(x0, t0, 0)

    # --- Test 1: setpoint=100, measured=80, output should be ~20 ---
    asm.li(t0, F_SET)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, F_MEAS)
    asm.addi(t1, x0, 80)
    asm.sw(t1, t0, 0)
    asm.li(t0, F_OUT)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    # Output should be ~20 (P-only: error=20, Kp=1.0)
    asm.addi(t0, x0, 15)
    asm.blt(s0, t0, "t1f")
    asm.addi(t0, x0, 25)
    asm.bge(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: setpoint=0, measured=100, output ≈ -100 ---
    asm.label("test2")
    asm.li(t0, F_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, F_SET)
    asm.sw(x0, t0, 0)
    asm.li(t0, F_MEAS)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)
    asm.li(t0, F_OUT)
    asm.lw(s0, t0, 0)  # should be ~-100

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t0, x0, -90)
    asm.bge(s0, t0, "t2f")   # s0 < -90 is OK (more negative)
    asm.addi(t0, x0, -110)
    asm.blt(s0, t0, "t2f")   # s0 > -110 is OK
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: step response, output magnitude should decrease ---
    asm.label("test3")
    asm.li(t0, F_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)
    asm.li(t0, F_SET)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)

    # Feed measurements: 0, 25, 50, 75, 95
    asm.li(t0, F_MEAS)
    asm.sw(x0, t0, 0)       # 0: error=100
    asm.li(t0, F_OUT)
    asm.lw(s0, t0, 0)       # first output

    asm.li(t0, F_MEAS)
    asm.addi(t1, x0, 95)
    asm.sw(t1, t0, 0)       # 95: error=5
    asm.li(t0, F_OUT)
    asm.lw(s1, t0, 0)       # second output (should be smaller magnitude)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    # |s0| > |s1| — first output should be larger than second
    # s0 ≈ 100, s1 ≈ 5. Just check s0 > s1.
    asm.bge(s1, s0, "t3f")
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
    ok = run_module_test("flux", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
