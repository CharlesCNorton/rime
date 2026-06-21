#!/usr/bin/env python3
"""SENTRY compositor test: RIME-I + memory protection unit.

Tests:
  1. Disabled MPU: any address → allowed
  2. Enable, configure region 0=[0x1000,+256] R/W. Check inside=allowed, outside=denied
  3. Check trap captures denied address
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

S_CADDR  = MOD_BASE + 0x000
S_CMODE  = MOD_BASE + 0x004
S_RESULT = MOD_BASE + 0x008
S_TRAP   = MOD_BASE + 0x00C
S_CTRL   = MOD_BASE + 0x010
S_R0BASE = MOD_BASE + 0x020
S_R0CFG  = MOD_BASE + 0x024


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

    def check_addr(addr, mode):
        asm.li(t0, S_CADDR)
        asm.li(t1, addr)
        asm.sw(t1, t0, 0)
        asm.li(t0, S_CMODE)
        asm.addi(t1, x0, mode)
        asm.sw(t1, t0, 0)

    def read_result(reg):
        asm.li(t0, S_RESULT)
        asm.lw(reg, t0, 0)
        asm.andi(reg, reg, 1)  # allowed bit

    asm.label("main")

    # --- Test 1: disabled, any address allowed ---
    asm.li(t0, S_CTRL)
    asm.sw(x0, t0, 0)  # disable

    check_addr(0x9999, 1)  # read
    read_result(s0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.beq(s0, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: enable, region 0 = [0x1000, +256], R+W ---
    asm.label("test2")
    asm.li(t0, S_R0BASE)
    asm.li(t1, 0x1000)
    asm.sw(t1, t0, 0)
    asm.li(t0, S_R0CFG)
    # size=256, R=1, W=1, enable=1 = 256 | (1<<16) | (1<<17) | (1<<18) = 0x70100
    asm.li(t1, 0x70100)
    asm.sw(t1, t0, 0)

    asm.li(t0, S_CTRL)
    asm.addi(t1, x0, 3)  # enable + clear trap
    asm.sw(t1, t0, 0)

    # Inside: 0x1080, read → allowed
    check_addr(0x1080, 1)
    read_result(s0)

    # Outside: 0x2000, read → denied
    check_addr(0x2000, 1)
    read_result(s1)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.beq(s0, x0, "t2f")  # inside should be allowed (1)
    asm.bne(s1, x0, "t2f")  # outside should be denied (0)
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: trap captures denied address ---
    asm.label("test3")
    asm.li(t0, S_RESULT)
    asm.lw(s0, t0, 0)
    asm.andi(s0, s0, 2)  # trapped bit

    asm.li(t0, S_TRAP)
    asm.lw(s1, t0, 0)  # should be 0x2000

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.beq(s0, x0, "t3f")
    asm.li(t0, 0x2000)
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
    ok = run_module_test("sentry", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
