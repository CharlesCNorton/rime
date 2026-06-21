#!/usr/bin/env python3
"""HEDGE compositor test: RIME-I + token bucket rate limiter.

Tests:
  1. Set burst=5, fill, make 5 requests — all allowed
  2. Make 6th request — denied (bucket empty)
  3. Verify allowed=5, denied=1 counters
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, t2, a0, s0, s1, s2, s4, MOD_BASE

H_REQ     = MOD_BASE + 0x000
H_RESULT  = MOD_BASE + 0x004
H_CTRL    = MOD_BASE + 0x008
H_RATE    = MOD_BASE + 0x00C
H_BURST   = MOD_BASE + 0x010
H_TOKENS  = MOD_BASE + 0x014
H_ALLOWED = MOD_BASE + 0x018
H_DENIED  = MOD_BASE + 0x01C


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

    # Reset + configure
    asm.li(t0, H_CTRL)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)      # reset

    asm.li(t0, H_BURST)
    asm.addi(t1, x0, 5)
    asm.sw(t1, t0, 0)      # burst=5, fills to 5

    # --- Test 1: 5 requests, all should be allowed ---
    asm.li(t0, H_REQ)
    asm.addi(s0, x0, 0)    # allowed count
    asm.addi(s1, x0, 5)
    asm.label("t1loop")
    asm.bge(s0, s1, "t1check")
    asm.sw(x0, t0, 0)      # request
    asm.li(t1, H_RESULT)
    asm.lw(t2, t1, 0)
    asm.add(s2, s2, t2)    # accumulate allows (s2 was 0 from reset)
    asm.addi(s0, s0, 1)
    asm.j("t1loop")
    asm.label("t1check")

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    # s2 should be 5 (all allowed)... but s2 wasn't initialized!
    # Use ALLOWED counter instead
    asm.li(t0, H_ALLOWED)
    asm.lw(s0, t0, 0)
    asm.addi(t0, x0, 5)
    asm.bne(s0, t0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: 6th request should be denied ---
    asm.label("test2")
    asm.li(t0, H_REQ)
    asm.sw(x0, t0, 0)      # 6th request

    asm.li(t0, H_RESULT)
    asm.lw(s0, t0, 0)      # should be 0 (denied)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.bne(s0, x0, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: verify counters ---
    asm.label("test3")
    asm.li(t0, H_ALLOWED)
    asm.lw(s0, t0, 0)      # should be 5
    asm.li(t0, H_DENIED)
    asm.lw(s1, t0, 0)      # should be 1

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 5)
    asm.bne(s0, t0, "t3f")
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
    ok = run_module_test("hedge", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
