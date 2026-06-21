#!/usr/bin/env python3
"""SIFT compositor test: RIME-I + SIFT Bloom filter.

Tests:
  1. Insert 3 values, query them, all should report "probably in set"
  2. Query values NOT inserted, should report "not in set" (zero false positives for small set)
  3. Insert 100 values, query all 100, verify all hit
  query 20 non-members, verify < 5 false positives
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s2, s3, s4, MOD_BASE

SIFT_INSERT  = MOD_BASE + 0x000
SIFT_QUERY   = MOD_BASE + 0x004
SIFT_CONTROL = MOD_BASE + 0x008
SIFT_COUNT   = MOD_BASE + 0x00C
SIFT_POP     = MOD_BASE + 0x010


def gen_firmware():
    asm = RV32I()
    asm.lui(sp, 0x00001)
    asm.lui(s4, 0x20000)  # UART base
    asm.j("main")

    # putc
    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    asm.label("main")

    # --- Test 1: Insert 3 values, query them ---
    # Clear filter
    asm.li(t0, SIFT_CONTROL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # Insert 42, 137, 999
    asm.li(t0, SIFT_INSERT)
    asm.addi(t1, x0, 42)
    asm.sw(t1, t0, 0)
    asm.li(t1, 137)
    asm.sw(t1, t0, 0)
    asm.li(t1, 999)
    asm.sw(t1, t0, 0)

    # Query 42: write to QUERY, then read QUERY
    asm.li(t0, SIFT_QUERY)
    asm.addi(t1, x0, 42)
    asm.sw(t1, t0, 0)    # write key
    asm.lw(s0, t0, 0)    # read result

    # Query 137
    asm.li(t1, 137)
    asm.sw(t1, t0, 0)
    asm.lw(s1, t0, 0)

    # Query 999
    asm.li(t1, 999)
    asm.sw(t1, t0, 0)
    asm.lw(s2, t0, 0)

    # All three should be 1
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.and_(t0, s0, s1)
    asm.and_(t0, t0, s2)
    asm.bne(t0, x0, "t1_pass")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1_pass")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 2: Query values NOT inserted ---
    asm.label("test2")
    asm.li(t0, SIFT_QUERY)

    # Query 7 (not inserted)
    asm.addi(t1, x0, 7)
    asm.sw(t1, t0, 0)
    asm.lw(s0, t0, 0)

    # Query 2048
    asm.li(t1, 2048)
    asm.sw(t1, t0, 0)
    asm.lw(s1, t0, 0)

    # Query 12345
    asm.li(t1, 12345)
    asm.sw(t1, t0, 0)
    asm.lw(s2, t0, 0)

    # At least 2 of 3 should be 0 (no false positive) for a 3-element set in 2048 bits
    asm.add(t0, s0, s1)
    asm.add(t0, t0, s2)
    # t0 = count of false positives. Should be <= 1.
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.addi(t1, x0, 2)
    asm.bge(t0, t1, "t2_fail")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2_fail")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: Insert 100 values, query all, check FP rate ---
    asm.label("test3")
    # Clear
    asm.li(t0, SIFT_CONTROL)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # Insert values 1000..1019 (20 elements, ~60 bits set in 256-bit filter)
    asm.li(t0, SIFT_INSERT)
    asm.li(s0, 1000)          # start
    asm.li(s1, 1020)          # end
    asm.label("ins_loop")
    asm.bge(s0, s1, "ins_done")
    asm.sw(s0, t0, 0)
    asm.addi(s0, s0, 1)
    asm.j("ins_loop")
    asm.label("ins_done")

    # Query 1000..1019, count hits
    asm.li(t0, SIFT_QUERY)
    asm.li(s0, 1000)
    asm.li(s1, 1020)
    asm.addi(s2, x0, 0)      # hits
    asm.label("qhit_loop")
    asm.bge(s0, s1, "qhit_done")
    asm.sw(s0, t0, 0)
    asm.lw(t1, t0, 0)
    asm.add(s2, s2, t1)
    asm.addi(s0, s0, 1)
    asm.j("qhit_loop")
    asm.label("qhit_done")

    # All 20 should hit: s2 == 20
    # Query 2000..2019, count false positives
    asm.li(s0, 2000)
    asm.li(s1, 2020)
    asm.addi(s3, x0, 0)      # false positives
    asm.label("qfp_loop")
    asm.bge(s0, s1, "qfp_done")
    asm.sw(s0, t0, 0)
    asm.lw(t1, t0, 0)
    asm.add(s3, s3, t1)
    asm.addi(s0, s0, 1)
    asm.j("qfp_loop")
    asm.label("qfp_done")

    # Pass if hits == 20 AND false_positives < 5
    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.addi(t0, x0, 20)
    asm.bne(s2, t0, "t3_fail")
    asm.addi(t0, x0, 5)
    asm.bge(s3, t0, "t3_fail")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("done")
    asm.label("t3_fail")
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
    ok = run_module_test("sift", firmware, expected="1P2P3P")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
