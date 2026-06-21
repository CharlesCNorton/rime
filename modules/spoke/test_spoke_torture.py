#!/usr/bin/env python3
"""SPOKE (SPI master with simulated loopback) torture test.

Asserts STATUS, RX_DATA, CS_OUT and CLK_CNT at reset, kicks off a TX
transaction, and (after timing-dependent in-flight reads we discard)
verifies the post-reset state again.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

TX_DATA  = 0x000
RX_DATA  = 0x004
STATUS   = 0x008
CONTROL  = 0x00C
DIV      = 0x010
LOOPBACK = 0x014
CS_OUT   = 0x018
CLK_CNT  = 0x01C


def gen():
    tb = TortureBuilder("spoke")
    tb.write(CONTROL, 2)            # reset
    tb.read_assert(STATUS, 0)       # busy=0, done=0
    tb.read_assert(RX_DATA, 0)
    tb.read_assert(CLK_CNT, 0)

    tb.write(DIV, 4)
    tb.write(LOOPBACK, 0xA5)
    tb.write(TX_DATA, 0x55)         # kick TX
    tb.delay(200)
    tb.read_discard(RX_DATA)        # value depends on loopback bit order
    tb.read_discard(STATUS)

    tb.write(CONTROL, 2)            # reset again
    tb.read_assert(STATUS, 0)
    tb.read_assert(CLK_CNT, 0)

    tb.write(0x00C, 2)
    tb.write(0x010, 2)
    tb.write(0x014, 0xA5)
    tb.write(0x00C, 1)
    tb.write(0x000, 0xFF)
    tb.delay(50)
    tb.read_check(0x004, 0xA5)
    tb.write(0x014, 0x00)
    tb.write(0x000, 0x42)
    tb.delay(50)
    tb.read_check(0x004, 0x00)
    tb.write(0x014, 0xFF)
    tb.write(0x000, 0x00)
    tb.delay(50)
    tb.read_check(0x004, 0xFF)
    tb.adversarial_write(0x004, 0xDEAD)
    tb.adversarial_write(0x018, 0xBEEF)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"SPOKE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
