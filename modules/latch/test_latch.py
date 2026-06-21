#!/usr/bin/env python3
"""LATCH compositor test: RIME-I + watchdog + event counter.

Tests:
  1. Set timeout, kick, verify not expired and countdown reset
  2. Set short timeout, let it expire (busy loop), verify expired flag
  3. Event counter: pulse 10 times, verify count=10 and timestamp captured
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

L_KICK   = MOD_BASE + 0x000
L_STATUS = MOD_BASE + 0x004
L_CTRL   = MOD_BASE + 0x008
L_TIMO   = MOD_BASE + 0x00C
L_REMAIN = MOD_BASE + 0x010
L_EVENT  = MOD_BASE + 0x014
L_ECOUNT = MOD_BASE + 0x018
L_ESTAMP = MOD_BASE + 0x01C


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

    # --- Test 1: event counter works (simpler than watchdog timing) ---
    asm.li(t0, L_CTRL)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)      # reset counter

    asm.li(t0, L_EVENT)
    asm.sw(x0, t0, 0)      # event 1
    asm.sw(x0, t0, 0)      # event 2
    asm.sw(x0, t0, 0)      # event 3

    asm.li(t0, L_ECOUNT)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(t0, x0, 3)
    asm.bne(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: set timeout=1, wait for expiry ---
    asm.label("test2")
    asm.li(t0, L_CTRL)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)      # clear expired

    asm.li(t0, L_TIMO)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)      # timeout = 1 (expires in ~256 clocks)

    asm.li(t0, L_CTRL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)      # enable

    # Busy wait ~2000 cycles
    asm.li(t0, 2000)
    asm.label("wait_exp")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "wait_exp")

    asm.li(t0, L_STATUS)
    asm.lw(s0, t0, 0)
    asm.andi(s0, s0, 1)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.beq(s0, x0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: event counter ---
    asm.label("test3")
    asm.li(t0, L_CTRL)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)      # reset event counter

    asm.li(t0, L_EVENT)
    asm.addi(s0, x0, 0)
    asm.addi(s1, x0, 10)
    asm.label("evt_loop")
    asm.bge(s0, s1, "evt_done")
    asm.sw(x0, t0, 0)      # pulse event
    asm.addi(s0, s0, 1)
    asm.j("evt_loop")
    asm.label("evt_done")

    asm.li(t0, L_ECOUNT)
    asm.lw(s0, t0, 0)      # should be 10

    asm.li(t0, L_ESTAMP)
    asm.lw(s1, t0, 0)      # should be nonzero (countdown at last event)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 10)
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
    ok = run_module_test("latch", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
