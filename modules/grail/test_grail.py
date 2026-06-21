#!/usr/bin/env python3
"""GRAIL compositor test: RIME-I + Merkle tree hasher.

Tests:
  1. All-zero leaves → deterministic root hash (nonzero)
  2. Change one leaf, root changes
  3. Set specific leaves, verify root matches Python computation
"""

import sys
import zlib
import struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import RV32I, run_module_test, x0, sp, t0, t1, a0, s0, s1, s4, MOD_BASE

G_LEAF = MOD_BASE + 0x000  # leaf[i] at +i*4
G_CTRL = MOD_BASE + 0x020
G_STAT = MOD_BASE + 0x024
G_ROOT = MOD_BASE + 0x028


def py_crc_pair(a, b):
    data = struct.pack('<II', a & 0xFFFFFFFF, b & 0xFFFFFFFF)
    return zlib.crc32(data) & 0xFFFFFFFF


def py_merkle(leaves):
    l1 = [py_crc_pair(leaves[i], leaves[i+1]) for i in range(0, 8, 2)]
    l2 = [py_crc_pair(l1[i], l1[i+1]) for i in range(0, 4, 2)]
    return py_crc_pair(l2[0], l2[1])


# Precompute expected roots
ROOT_ZEROS = py_merkle([0]*8)
ROOT_ONES  = py_merkle([1,0,0,0,0,0,0,0])
ROOT_SEQ   = py_merkle(list(range(8)))


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

    _gw_cnt = [0]
    def compute_and_wait():
        n = _gw_cnt[0]
        _gw_cnt[0] += 1
        asm.li(t0, G_CTRL)
        asm.addi(t1, x0, 1)
        asm.sw(t1, t0, 0)
        asm.li(t0, G_STAT)
        lbl = f"gw{n}"
        asm.label(lbl)
        asm.lw(t1, t0, 0)
        asm.beq(t1, x0, lbl)

    asm.label("main")

    # --- Test 1: all-zero leaves → nonzero root ---
    asm.li(t0, G_LEAF)
    for i in range(8):
        asm.sw(x0, t0, i * 4)
    compute_and_wait()
    asm.li(t0, G_ROOT)
    asm.lw(s0, t0, 0)

    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.beq(s0, x0, "t1f")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test2")
    asm.label("t1f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 2: change leaf[0] to 1, root should differ ---
    asm.label("test2")
    asm.li(t0, G_LEAF)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)  # leaf[0] = 1
    compute_and_wait()
    asm.li(t0, G_ROOT)
    asm.lw(s1, t0, 0)

    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.beq(s0, s1, "t2f")  # roots should differ
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("test3")
    asm.label("t2f")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    # --- Test 3: leaves = 0..7, verify root matches Python ---
    asm.label("test3")
    asm.li(t0, G_LEAF)
    for i in range(8):
        asm.addi(t1, x0, i)
        asm.sw(t1, t0, i * 4)
    compute_and_wait()
    asm.li(t0, G_ROOT)
    asm.lw(s0, t0, 0)
    asm.li(s1, ROOT_SEQ)

    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.bne(s0, s1, "t3f")
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
    print(f"Expected: zeros=0x{ROOT_ZEROS:08X} seq=0x{ROOT_SEQ:08X}")
    firmware = gen_firmware()
    ok = run_module_test("grail", firmware)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
