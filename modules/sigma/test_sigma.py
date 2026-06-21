#!/usr/bin/env python3
"""SIGMA compositor test: RIME-I + Fletcher-16 checksum.

Tests:
  1. Empty checksum = 0
  2. Feed "AB" (0x41, 0x42), verify against Python Fletcher-16
  3. Feed 256-byte ramp, verify checksum and count
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s4, MOD_BASE

S_DATA = MOD_BASE + 0x000
S_CKSM = MOD_BASE + 0x004
S_CTRL = MOD_BASE + 0x008
S_CNT  = MOD_BASE + 0x00C


def fletcher16(data):
    s1, s2 = 0, 0
    for b in data:
        s1 = (s1 + b) % 255
        s2 = (s2 + s1) % 255
    return (s2 << 8) | s1


F16_AB = fletcher16([0x41, 0x42])
F16_RAMP = fletcher16(range(256))


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
        asm.li(t0, S_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    def feed(val):
        asm.li(t0, S_DATA)
        asm.addi(t1, x0, val)
        asm.sw(t1, t0, 0)

    asm.label("main")

    # --- Test 1: empty = 0 ---
    reset()
    asm.li(t0, S_CKSM)
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

    # --- Test 2: "AB" ---
    asm.label("test2")
    reset()
    feed(0x41)
    feed(0x42)
    asm.li(t0, S_CKSM)
    asm.lw(s0, t0, 0)
    asm.li(s1, F16_AB)
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.bne(s0, s1, "t2f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: 0-255 ramp ---
    asm.label("test3")
    reset()
    asm.li(t0, S_DATA)
    asm.addi(s0, x0, 0)
    asm.li(s1, 256)
    asm.label("ramp")
    asm.bge(s0, s1, "ramp_done")
    asm.sw(s0, t0, 0)
    asm.addi(s0, s0, 1)
    asm.j("ramp")
    asm.label("ramp_done")

    asm.li(t0, S_CKSM)
    asm.lw(s0, t0, 0)
    asm.li(s1, F16_RAMP)
    asm.li(t0, S_CNT)
    asm.lw(s2, t0, 0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(s0, s1, "t3f")
    asm.li(t0, 256)
    asm.bne(s2, t0, "t3f")
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
    print(f"Fletcher-16: AB=0x{F16_AB:04X} ramp=0x{F16_RAMP:04X}")
    firmware = gen_firmware()
    ok = run_module_test("sigma", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
