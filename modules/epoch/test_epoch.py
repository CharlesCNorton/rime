#!/usr/bin/env python3
"""EPOCH compositor test: RIME-I + real-time clock.

Tests:
  1. Set time to 23:59:58, enable, wait ~2 seconds worth of ticks, check rollover to 00:00:00 day+1
     (Can't wait real seconds in firmware. Instead: set sec=58, enable, read ticks > 0 = clock running)
  2. Set time, read back, verify values match
  3. Check uptime increments (read twice with delay, second > first)

Since we can't wait real seconds in a fast test, we verify the tick
counter is incrementing (proving the divider works) and that register
set/get is correct.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s3, s4, MOD_BASE

E_SEC  = MOD_BASE + 0x000
E_MIN  = MOD_BASE + 0x004
E_HOUR = MOD_BASE + 0x008
E_DAY  = MOD_BASE + 0x00C
E_CTRL = MOD_BASE + 0x010
E_TICK = MOD_BASE + 0x014
E_UP   = MOD_BASE + 0x018


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

    # --- Test 1: enable clock, verify ticks are incrementing ---
    asm.li(t0, E_CTRL)
    asm.addi(t1, x0, 3)    # enable + reset
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 1)    # enable only
    asm.sw(t1, t0, 0)

    # Small delay to let ticks accumulate
    asm.li(t0, 1000)
    asm.label("tick_wait")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "tick_wait")

    asm.li(t0, E_TICK)
    asm.lw(s0, t0, 0)      # should be > 0

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.beq(s0, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: set time, read back ---
    asm.label("test2")
    asm.li(t0, E_SEC)
    asm.addi(t1, x0, 42)
    asm.sw(t1, t0, 0)
    asm.li(t0, E_MIN)
    asm.addi(t1, x0, 30)
    asm.sw(t1, t0, 0)
    asm.li(t0, E_HOUR)
    asm.addi(t1, x0, 15)
    asm.sw(t1, t0, 0)
    asm.li(t0, E_DAY)
    asm.addi(t1, x0, 100)
    asm.sw(t1, t0, 0)

    # Read back
    asm.li(t0, E_SEC)
    asm.lw(s0, t0, 0)
    asm.li(t0, E_MIN)
    asm.lw(s1, t0, 0)
    asm.li(t0, E_HOUR)
    asm.lw(s2, t0, 0)
    asm.li(t0, E_DAY)
    asm.lw(s3, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    # sec might have ticked to 43 by now, check >= 42
    asm.addi(t0, x0, 42)
    asm.blt(s0, t0, "t2f")
    asm.addi(t0, x0, 30)
    asm.bne(s1, t0, "t2f")
    asm.addi(t0, x0, 15)
    asm.bne(s2, t0, "t2f")
    asm.addi(t0, x0, 100)
    asm.bne(s3, t0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: ticks increase between two reads ---
    asm.label("test3")
    asm.li(t0, E_TICK)
    asm.lw(s0, t0, 0)

    asm.li(t0, 500)
    asm.label("t3wait")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "t3wait")

    asm.li(t0, E_TICK)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    # s1 should be > s0 (ticks increased)
    asm.bge(s0, s1, "t3f")
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
    ok = run_module_test("epoch", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
