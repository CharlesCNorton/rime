#!/usr/bin/env python3
"""KOLMOGOROV hash-based torture test.

Exercises the register interface: target, search length, control,
status, single-program run, init values. The K estimation requires
many clock cycles so the offline test exercises configuration and
single-run paths.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

TARGET      = 0x000
CONTROL     = 0x004
STATUS      = 0x008
K_RESULT    = 0x00C
K_PROGRAM   = 0x010
PROGRAM     = 0x014
RUN_OUTPUT  = 0x018
INIT_A      = 0x01C
INIT_B      = 0x020
BATCH_NUM   = 0x024
PROGS_TRIED = 0x028
SEARCH_LEN  = 0x02C
MATCHES     = 0x030


def gen():
    tb = TortureBuilder("kolmogorov")

    # Initial state
    tb.read_mix(STATUS)

    # Set target
    tb.write(TARGET, 42)

    # Set search length
    tb.write(SEARCH_LEN, 6)
    tb.read_check(SEARCH_LEN, 6)

    # Set init values
    tb.write(INIT_A, 0)
    tb.write(INIT_B, 0)

    # Single-program run: program = INC INC INC (A becomes 3)
    # INC=0, so program = 0b000_000_000_000_000_000 = 0x00000
    # Wait, INC INC INC INC... 6x INC = A goes from 0 to 6
    # Encoding: all zeros = 6 INC instructions
    tb.write(PROGRAM, 0x00000)
    tb.write(CONTROL, 0x02)  # start single run

    # Wait a few cycles
    tb.delay(50)
    tb.read_mix(STATUS)
    tb.read_mix(RUN_OUTPUT)  # should be 6 (6 INC from 0), halted

    # Program = DEC (opcode 1) × 6 = all 1s in 3-bit fields = 0x09249
    # Actually: opcode 1 = 001, six of them: 001_001_001_001_001_001 = 0x09249
    tb.write(PROGRAM, 0x09249)
    tb.write(CONTROL, 0x02)
    tb.delay(50)
    tb.read_mix(RUN_OUTPUT)  # A = 0 - 6 = 250 (wraps)

    # Adversarial
    tb.adversarial_write(CONTROL, 0xFFFFFFFF)
    tb.adversarial_write(SEARCH_LEN, 0)
    tb.adversarial_write(TARGET, 0xFF)

    tb.read_mix(STATUS)
    tb.read_mix(PROGS_TRIED)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"KOLMOGOROV torture: {len(firmware)} instrs, expected 0x{expected:08X}")


if __name__ == "__main__":
    main()
