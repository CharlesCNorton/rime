#!/usr/bin/env python3
"""CAIRN hash-based torture test.

Exercises every stack operation: PUSH, POP, PEEK, DUP, SWAP, DROP,
ADD, SUB, MUL, AND, OR, XOR, NOT, LT, EQ, DEPTH, CLEAR.

Adversarial: pop empty stack, push when full (16 deep), overflow
arithmetic, operate on single-element stack.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder, u32

PUSH  = 0x000
POP   = 0x004
PEEK  = 0x008
OP    = 0x00C
DEPTH = 0x010
CTRL  = 0x014

OP_NOP=0
OP_DUP=1
OP_SWAP=2
OP_DROP=3
OP_ADD=4
OP_SUB=5
OP_MUL=6
OP_AND=7
OP_OR=8
OP_XOR=9
OP_NOT=10
OP_LT=11
OP_EQ=12


def gen():
    tb = TortureBuilder("cairn")

    # Clear stack
    tb.reset(CTRL, bit=0)
    tb.read_check(DEPTH, 0)

    # Adversarial: pop empty stack (should return 0 and stay at depth 0)
    tb.read_mix(POP, 0)
    tb.read_check(DEPTH, 0)

    # Push 3 values: 10, 20, 30
    tb.write(PUSH, 10)
    tb.write(PUSH, 20)
    tb.write(PUSH, 30)
    tb.read_check(DEPTH, 3)
    tb.read_check(PEEK, 30)

    # DUP: stack = [10, 20, 30, 30]
    tb.write(OP, OP_DUP)
    tb.read_check(DEPTH, 4)
    tb.read_check(PEEK, 30)

    # DROP: stack = [10, 20, 30]
    tb.write(OP, OP_DROP)
    tb.read_check(DEPTH, 3)

    # SWAP: stack = [10, 30, 20]
    tb.write(OP, OP_SWAP)
    tb.read_check(PEEK, 20)

    # ADD: 30 + 20 = 50, stack = [10, 50]
    # Wait — after SWAP, TOS=20, NOS=30. ADD pops both, pushes NOS+TOS=50.
    # Actually CAIRN does: stack[sp-2] <= nos + tos; sp <= sp-1
    # So after SWAP: stack=[10,30,20], ADD: stack[1]=30+20=50, sp=2 -> stack=[10,50]
    tb.write(OP, OP_ADD)
    tb.read_check(PEEK, 50)
    tb.read_check(DEPTH, 2)

    # SUB: 10 - 50 = -40 (unsigned: 0xFFFFFFD8). NOS=10, TOS=50.
    tb.write(OP, OP_SUB)
    tb.read_check(PEEK, u32(10 - 50))
    tb.read_check(DEPTH, 1)

    # Push values for MUL test: 7 * 6 = 42
    tb.write(PUSH, 7)
    tb.write(PUSH, 6)
    tb.write(OP, OP_MUL)
    tb.read_check(PEEK, 42)

    # POP the result, mix into hash
    tb.read_check(POP, 42)

    # Push for logic ops
    tb.reset(CTRL, bit=0)
    tb.write(PUSH, 0xFF00FF00)
    tb.write(PUSH, 0x0F0F0F0F)

    # AND: 0xFF00FF00 & 0x0F0F0F0F = 0x0F000F00
    tb.write(OP, OP_AND)
    tb.read_check(PEEK, 0x0F000F00)

    # Push another for OR
    tb.write(PUSH, 0xF0F0F0F0)
    # OR: 0x0F000F00 | 0xF0F0F0F0 = 0xFFF0FFF0
    tb.write(OP, OP_OR)
    tb.read_check(PEEK, 0xFFF0FFF0)

    # Push for XOR
    tb.write(PUSH, 0xFFFFFFFF)
    # XOR: 0xFFF0FFF0 ^ 0xFFFFFFFF = 0x000F000F
    tb.write(OP, OP_XOR)
    tb.read_check(PEEK, 0x000F000F)

    # NOT: ~0x000F000F = 0xFFF0FFF0
    tb.write(OP, OP_NOT)
    tb.read_check(PEEK, 0xFFF0FFF0)

    # LT and EQ
    tb.reset(CTRL, bit=0)
    tb.write(PUSH, 5)
    tb.write(PUSH, 10)
    tb.write(OP, OP_LT)   # 5 < 10 -> 1
    tb.read_check(PEEK, 1)

    tb.write(PUSH, 7)
    tb.write(OP, OP_EQ)   # 1 == 7 -> 0
    tb.read_check(PEEK, 0)

    # Adversarial: fill stack to capacity (16)
    tb.reset(CTRL, bit=0)
    for i in range(16):
        tb.write(PUSH, i * 11)
    tb.read_check(DEPTH, 16)

    # Adversarial: push when full (should be ignored)
    tb.write(PUSH, 0xDEAD)
    tb.read_check(DEPTH, 16)
    tb.read_check(PEEK, 15 * 11)  # TOS should still be last valid push

    # Pop everything and verify last value
    for _ in range(15):
        tb.read_mix(POP, None)  # don't check intermediate values
    tb.read_check(POP, 0)  # first pushed value was 0
    tb.read_check(DEPTH, 0)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"CAIRN torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    from compositor_test import build_module, flash_and_read, restore_rime
    from compositor_template import generate_top_sv
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("cairn", firmware, mod_dir / "top.sv")
    ok, luts = build_module("cairn", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("cairn")
    print(f"Output: {output[:80]!r}")
    restore_rime()
    return 0 if "PASS" in output.split('\n')[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
