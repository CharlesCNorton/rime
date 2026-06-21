#!/usr/bin/env python3
"""EMBER hash-based torture test.

Exercises the EMBER register interface: status, warmup, ring frequency,
stuck bitmap, XOR topology selection, auto-rotation config, entropy count.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

ENTROPY     = 0x000
STATUS      = 0x004
RING_FREQ   = 0x008
STUCK       = 0x00C
WARMUP      = 0x010
CONTROL     = 0x014
HEALTH      = 0x018
TOPOLOGY    = 0x01C
ENT_COUNT   = 0x020
RAW_BYTE    = 0x024
AUTO_ROTATE = 0x028
ROTATE_INT  = 0x02C


def gen():
    tb = TortureBuilder("ember")

    tb.read_mix(STATUS)
    tb.read_mix(WARMUP)
    tb.read_mix(RING_FREQ)
    tb.read_mix(STUCK)
    tb.read_mix(HEALTH)
    tb.read_check(ENT_COUNT, 0)

    # Topology starts at 0 with 0 switches
    tb.read_check(TOPOLOGY, 0x00000000)

    # Select topology 1 via CONTROL[2:1]
    tb.write(CONTROL, 0x00000002)
    tb.read_mix(TOPOLOGY)

    # Select topology 3
    tb.write(CONTROL, 0x00000006)
    tb.read_mix(TOPOLOGY)

    # Back to topology 0
    tb.write(CONTROL, 0x00000000)
    tb.read_mix(TOPOLOGY)

    # Configure auto-rotation
    tb.write(ROTATE_INT, 512)
    tb.read_check(ROTATE_INT, 512)
    tb.write(AUTO_ROTATE, 1)
    tb.read_check(AUTO_ROTATE, 1)

    # Disable auto-rotation
    tb.write(AUTO_ROTATE, 0)
    tb.read_check(AUTO_ROTATE, 0)

    # Adversarial
    tb.adversarial_write(CONTROL, 0xFFFFFFFF)
    tb.adversarial_write(CONTROL, 0x00000000)
    tb.adversarial_write(ROTATE_INT, 0)
    tb.adversarial_write(ROTATE_INT, 0xFFFFFFFF)

    tb.read_mix(RAW_BYTE)
    tb.read_mix(STATUS)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"EMBER torture: {len(firmware)} instrs, expected 0x{expected:08X}")


if __name__ == "__main__":
    main()
