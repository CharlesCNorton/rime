#!/usr/bin/env python3
"""IRIS hash-based torture test.

Exercises the IRIS register interface: status, sample list configuration,
rate setting, buffer control, frame/sample counters. DMA reads require
another module to be present, so the offline torture test exercises
the configuration and readback paths.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

STATUS      = 0x000
CONTROL     = 0x004
SAMPLE_CNT  = 0x008
FRAME_CNT   = 0x00C
LIST_LEN    = 0x010
LIST_RATE   = 0x014
BUF_RD      = 0x018
BUF_LEVEL   = 0x01C
MANIFEST    = 0x020
SAMPLE_LIST = 0x100
SAMPLE_TAG  = 0x140


def gen():
    tb = TortureBuilder("iris")

    # Initial state: not running, empty buffer
    tb.read_mix(STATUS)
    tb.read_check(SAMPLE_CNT, 0)
    tb.read_check(FRAME_CNT, 0)
    tb.read_check(BUF_LEVEL, 0)

    # Configure sample list: 4 entries targeting hypothetical module addresses
    tb.write(SAMPLE_LIST + 0, 0x30000000)  # module 0, register 0
    tb.write(SAMPLE_LIST + 4, 0x30000004)  # module 0, register 4
    tb.write(SAMPLE_LIST + 8, 0x31000000)  # module 1, register 0
    tb.write(SAMPLE_LIST + 12, 0x31000008) # module 1, register 8

    # Read back sample list
    tb.read_check(SAMPLE_LIST + 0, 0x30000000)
    tb.read_check(SAMPLE_LIST + 4, 0x30000004)
    tb.read_check(SAMPLE_LIST + 8, 0x31000000)
    tb.read_check(SAMPLE_LIST + 12, 0x31000008)

    # Configure tags
    tb.write(SAMPLE_TAG + 0, 0x00300001)
    tb.write(SAMPLE_TAG + 4, 0x00300002)
    tb.read_check(SAMPLE_TAG + 0, 0x00300001)
    tb.read_check(SAMPLE_TAG + 4, 0x00300002)

    # Set list length and rate
    tb.write(LIST_LEN, 4)
    tb.read_check(LIST_LEN, 4)
    tb.write(LIST_RATE, 1000)
    tb.read_check(LIST_RATE, 1000)

    # Clear buffer
    tb.write(CONTROL, 0x04)  # bit 2 = clear
    tb.read_check(BUF_LEVEL, 0)

    # Adversarial
    tb.adversarial_write(CONTROL, 0xFFFFFFFF)
    tb.adversarial_write(LIST_LEN, 0)
    tb.adversarial_write(LIST_LEN, 20)  # > 16 should clamp
    tb.adversarial_write(LIST_RATE, 0)

    # Read status
    tb.read_mix(STATUS)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"IRIS torture: {len(firmware)} instrs, expected 0x{expected:08X}")


if __name__ == "__main__":
    main()
