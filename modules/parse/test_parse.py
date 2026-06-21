#!/usr/bin/env python3
"""PARSE compositor test: RIME-I + NFA regex engine (8-state).

Tests:
  1. Configure state 0 as accept+init, check STATUS shows accept immediately
  2. Match "AB": S0('A')->S1, S1('B')->S2(accept), feed "AB", check accept
  3. Match "RIME": S0-S3 chain, feed "XRIME", check accept after 'E'
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s4, MOD_BASE

P_IN   = MOD_BASE + 0x000
P_STAT = MOD_BASE + 0x004
P_CTRL = MOD_BASE + 0x008
P_MATCH = MOD_BASE + 0x00C
P_CFG  = MOD_BASE + 0x100


def cfg_word(match_byte, hit, miss, accept, init):
    """Build a 16-bit config word for one NFA state."""
    return (match_byte & 0xFF) | ((hit & 7) << 8) | ((miss & 7) << 11) | ((accept & 1) << 14) | ((init & 1) << 15)


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

    def write_cfg(state_idx, word):
        asm.li(t0, P_CFG + state_idx * 4)
        asm.li(t1, word)
        asm.sw(t1, t0, 0)

    def reset_nfa():
        asm.li(t0, P_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)

    def feed_byte(byte_val):
        asm.li(t0, P_IN)
        asm.addi(t1, x0, byte_val)
        asm.sw(t1, t0, 0)

    def read_accept_into(reg):
        asm.li(t0, P_STAT)
        asm.lw(reg, t0, 0)
        asm.andi(reg, reg, 1)

    asm.label("main")

    # --- Test 1: state 0 = accept + init, check accept without feeding anything ---
    write_cfg(0, cfg_word(0, 0, 7, accept=1, init=1))
    reset_nfa()
    read_accept_into(s0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.bne(s0, x0, "t1p")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1p")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 2: match "AB" ---
    # S0: match 'A', hit->S1, miss->stay(7), no accept, init=1
    # S1: match 'B', hit->S2, miss->S0(0), no accept, no init
    # S2: accept, stay
    asm.label("test2")
    write_cfg(0, cfg_word(ord('A'), hit=1, miss=7, accept=0, init=1))
    write_cfg(1, cfg_word(ord('B'), hit=2, miss=0, accept=0, init=0))
    write_cfg(2, cfg_word(0, hit=2, miss=7, accept=1, init=0))
    reset_nfa()

    feed_byte(ord('A'))
    feed_byte(ord('B'))
    read_accept_into(s0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.bne(s0, x0, "t2p")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2p")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 3: match "RIME" in "XRIME" ---
    asm.label("test3")
    write_cfg(0, cfg_word(ord('R'), hit=1, miss=0, accept=0, init=1))
    write_cfg(1, cfg_word(ord('I'), hit=2, miss=0, accept=0, init=0))
    write_cfg(2, cfg_word(ord('M'), hit=3, miss=0, accept=0, init=0))
    write_cfg(3, cfg_word(ord('E'), hit=4, miss=0, accept=0, init=0))
    write_cfg(4, cfg_word(0, hit=4, miss=7, accept=1, init=0))
    reset_nfa()

    feed_byte(ord('X'))
    feed_byte(ord('R'))
    feed_byte(ord('I'))
    feed_byte(ord('M'))
    feed_byte(ord('E'))
    read_accept_into(s0)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(s0, x0, "t3p")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("done")
    asm.label("t3p")
    asm.addi(a0, x0, ord('P'))
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
    ok = run_module_test("parse", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
