#!/usr/bin/env python3
"""RIME-I hash-based torture test (adapter for torture_sweep.py).

Delegates to test_isa.gen_firmware() which threads a 32-bit hash
through every RV32I instruction.  See test_isa.py for the algorithm.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_isa import gen_firmware  # noqa: E402


def gen():
    return gen_firmware()


if __name__ == "__main__":
    fw, expected = gen()
    print(f"RIME-I torture: {len(fw)} instrs, expected 0x{expected:08X}")
