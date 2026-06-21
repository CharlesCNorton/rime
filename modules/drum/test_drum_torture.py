#!/usr/bin/env python3
"""Torture test for DRUM: DRUM: Driven Register Utility for Microsequencing — 16-instruction programmable sequencer with output port

Hash-based register exercise using TortureBuilder. Threads a running
hash through every register write and read the module supports, with
adversarial sequences for boundary values and read-only violations.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder


def gen():
    tb = TortureBuilder("drum")
    tb.write(0x04C, 2)             # reset
    # Program: OUT 0x42, OUT 0x43, HALT
    tb.write(0x000, (1 << 28) | 0x42)
    tb.write(0x004, (1 << 28) | 0x43)
    tb.write(0x008, (4 << 28))
    tb.write(0x04C, 1)             # start
    tb.delay(20)
    tb.read_check(0x040, 0x43)     # last OUT value
    tb.read_check(0x048, 2)        # halted

    # Adversarial: boundary operand values
    tb.write(0x04C, 2)             # reset
    tb.write(0x000, (1 << 28) | 0xFF)   # OUT 0xFF
    tb.write(0x004, (1 << 28) | 0x00)   # OUT 0x00
    tb.write(0x008, (2 << 28) | 1)      # WAIT 1
    tb.write(0x00C, (1 << 28) | 0xAA)   # OUT 0xAA
    tb.write(0x010, (3 << 28) | 0x04)   # JMP 4 (self-targeting next)
    tb.write(0x014, (4 << 28))           # HALT (reached by JMP to 4 = index 5?  no, JMP target is instruction index)
    # Fix: JMP to index 5 which is HALT
    tb.write(0x010, (3 << 28) | 0x05)   # JMP 5
    tb.write(0x014, (4 << 28))           # HALT
    tb.write(0x04C, 1)                    # start
    tb.delay(30)
    tb.read_check(0x040, 0xAA)           # last OUT value
    tb.read_check(0x048, 2)              # halted

    # Adversarial: garbage writes to read-only registers
    tb.adversarial_write(0x040, 0xFFFFFFFF)
    tb.adversarial_write(0x044, 0xDEADBEEF)
    tb.adversarial_write(0x048, 0x12345678)

    # Adversarial: re-read after garbage writes (should be unchanged)
    tb.read_check(0x040, 0xAA)
    tb.read_check(0x048, 2)

    # Program all 16 slots then reset without starting
    for i in range(16):
        tb.write(i * 4, (1 << 28) | (i & 0xFF))
    tb.write(0x04C, 2)  # reset
    tb.read_check(0x048, 0)  # not halted, not running

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"DRUM torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
