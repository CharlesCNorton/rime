#!/usr/bin/env python3
"""WIRE (I2C master with simulated loopback) torture test.

Validates observable state after reset using read_assert: STATUS == 0
and STATE == 0 (S_IDLE) after CONTROL bit 2 (reset). RX_DATA is 0 at
reset. LOOPBACK is write-only. The TX sequence itself is timing-
dependent, so we only assert the pre- and post-reset states.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from torture_gen import TortureBuilder

ADDR     = 0x000
TX_DATA  = 0x004
RX_DATA  = 0x008
CONTROL  = 0x00C
STATUS   = 0x010
LOOPBACK = 0x014
STATE    = 0x018


def gen():
    tb = TortureBuilder("wire")
    tb.write(CONTROL, 0x04)         # reset
    tb.read_assert(STATUS, 0)       # busy=0, done=0, nack=0
    tb.read_assert(STATE, 0)        # S_IDLE
    tb.read_assert(RX_DATA, 0)      # no data received yet

    tb.write(LOOPBACK, 0x99)
    tb.write(ADDR, 0x50)
    tb.write(TX_DATA, 0x42)

    tb.read_assert(STATUS, 0)       # still idle until start bit
    tb.read_assert(STATE, 0)

    tb.write(CONTROL, 0x01)         # kick off TX
    tb.delay(2000)
    tb.read_discard(STATUS)         # in-flight state — not asserted
    tb.read_discard(STATE)

    tb.write(CONTROL, 0x04)         # reset again
    tb.read_assert(STATUS, 0)
    tb.read_assert(STATE, 0)


    tb.write(0x00C, 4)
    tb.write(0x014, 0x42)
    tb.write(0x000, 0x50)
    tb.write(0x004, 0xAB)
    tb.write(0x00C, 1)
    tb.delay(100)
    tb.read_mix(0x010, None)
    tb.write(0x00C, 8)
    tb.delay(20)
    tb.write(0x000, 0xD0)
    tb.write(0x00C, 2)
    tb.delay(100)
    tb.read_check(0x008, 0x42)
    tb.adversarial_write(0x008, 0xDEAD)
    tb.adversarial_write(0x010, 0xBEEF)
    tb.adversarial_write(0x018, 0)
    tb.write(0x00C, 4)

    return tb.finish()


def main():
    firmware, expected = gen()
    print(f"WIRE torture: {len(firmware)} instrs, expected 0x{expected:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
