#!/usr/bin/env python3
"""PERIPHERAL composition: 9 new modules silicon verification.

Exercises CLASP, GPIO, PULSE, SPOKE, WIRE, FERRY, ARBOR, PYLON, DRUM
with known inputs and prints labelled hex readbacks.

Usage:
    python modules/compositions/peripheral.py --gen-only
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rime-i"))

_gf_src = (Path(__file__).resolve().parent.parent / "rime-i" / "gen_firmware.py").read_text()
_gf_ns = {}
exec(_gf_src.split("\ndef generate_math_firmware")[0], _gf_ns)
RV32I = _gf_ns["RV32I"]

x0, ra, sp = 0, 1, 2
t0, t1, t2 = 5, 6, 7
a0, a1 = 10, 11
s0, s1, s2, s3, s4, s5, s6, s7 = 8, 9, 18, 19, 20, 21, 22, 23

UART = 0x20000000

CLASP = 0x30000000
GPIO  = 0x31000000
PULSE = 0x32000000
SPOKE = 0x33000000
WIRE  = 0x34000000
FERRY = 0x35000000
ARBOR = 0x36000000
PYLON = 0x37000000
DRUM  = 0x38000000

PERIPHERAL_MODULES = [
    "clasp", "gpio", "pulse", "spoke", "wire", "ferry",
    "arbor", "pylon", "drum",
]


def emit_prelude(asm):
    asm.lui(sp, 0x00001)
    asm.lui(s4, 0x20000)
    asm.j("main")

    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    asm.label("puthex")
    asm.addi(sp, sp, -12)
    asm.sw(ra, sp, 8)
    asm.sw(s0, sp, 4)
    asm.sw(s1, sp, 0)
    asm.mv(s0, a0)
    asm.addi(s1, x0, 28)
    asm.label("ph_loop")
    asm.blt(s1, x0, "ph_done")
    asm.srl(a0, s0, s1)
    asm.andi(a0, a0, 0xF)
    asm.addi(t0, x0, 10)
    asm.blt(a0, t0, "ph_digit")
    asm.addi(a0, a0, ord('A') - 10)
    asm.j("ph_emit")
    asm.label("ph_digit")
    asm.addi(a0, a0, ord('0'))
    asm.label("ph_emit")
    asm.call("putc")
    asm.addi(s1, s1, -4)
    asm.j("ph_loop")
    asm.label("ph_done")
    asm.lw(s1, sp, 0)
    asm.lw(s0, sp, 4)
    asm.lw(ra, sp, 8)
    asm.addi(sp, sp, 12)
    asm.ret()


def print_label(asm, label, value_reg):
    for ch in label:
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, ord(':'))
    asm.call("putc")
    asm.mv(a0, value_reg)
    asm.call("puthex")
    asm.addi(a0, x0, 10)
    asm.call("putc")


def generate_firmware():
    asm = RV32I()
    emit_prelude(asm)

    asm.label("main")

    # CLASP: clear, acquire slot 0, then slot 1, read state
    asm.li(t0, CLASP + 0x044)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # clear
    asm.li(t0, CLASP + 0x000)
    asm.lw(s0, t0, 0)              # acquire slot 0 (should be 0 = was free)
    print_label(asm, "CLASPA1", s0)
    asm.li(t0, CLASP + 0x004)
    asm.lw(s0, t0, 0)              # acquire slot 1 (should be 0 = was free)
    print_label(asm, "CLASPA2", s0)
    asm.li(t0, CLASP + 0x040)
    asm.lw(s0, t0, 0)              # state (slots 0+1 set => 0x03)
    print_label(asm, "CLASPST", s0)

    # GPIO: configure dir, write output, read pin
    asm.li(t0, GPIO + 0x000)
    asm.li(t1, 0xFFFF)
    asm.sw(t1, t0, 0)              # all output
    asm.li(t0, GPIO + 0x004)
    asm.li(t1, 0x55AA)
    asm.sw(t1, t0, 0)
    asm.li(t0, GPIO + 0x00C)
    asm.lw(s0, t0, 0)              # pin
    print_label(asm, "GPIO", s0)

    # PULSE: configure ch0 period=10 duty=5, enable, sample output
    asm.li(t0, PULSE + 0x024)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, PULSE + 0x000)
    asm.addi(t1, x0, 10)
    asm.sw(t1, t0, 0)              # period
    asm.li(t0, PULSE + 0x004)
    asm.addi(t1, x0, 5)
    asm.sw(t1, t0, 0)              # duty
    asm.li(t0, PULSE + 0x024)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # enable
    asm.li(t2, 50)
    asm.label("pulse_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "pulse_w")
    asm.li(t0, PULSE + 0x028)
    asm.lw(s0, t0, 0)              # counter (just exercise)
    print_label(asm, "PULSE", s0)

    # SPOKE: reset, configure loopback, send a byte, read RX
    asm.li(t0, SPOKE + 0x00C)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)
    asm.li(t0, SPOKE + 0x010)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)              # divider
    asm.li(t0, SPOKE + 0x014)
    asm.addi(t1, x0, 0xA5)
    asm.sw(t1, t0, 0)              # loopback
    asm.li(t0, SPOKE + 0x000)
    asm.addi(t1, x0, 0x55)
    asm.sw(t1, t0, 0)              # TX
    asm.li(t2, 100)
    asm.label("sp_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "sp_w")
    asm.li(t0, SPOKE + 0x008)
    asm.lw(s0, t0, 0)              # status
    print_label(asm, "SPOKE", s0)

    # WIRE: reset, set addr, start tx, read status
    asm.li(t0, WIRE + 0x00C)
    asm.addi(t1, x0, 4)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, WIRE + 0x000)
    asm.addi(t1, x0, 0x50)
    asm.sw(t1, t0, 0)              # addr
    asm.li(t0, WIRE + 0x004)
    asm.addi(t1, x0, 0x42)
    asm.sw(t1, t0, 0)              # tx data
    asm.li(t0, WIRE + 0x00C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # start tx
    asm.li(t2, 60)
    asm.label("w_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "w_w")
    asm.li(t0, WIRE + 0x010)
    asm.lw(s0, t0, 0)              # status
    print_label(asm, "WIRE", s0)

    # FERRY: reset, fill scratch, copy
    asm.li(t0, FERRY + 0x04C)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, FERRY + 0x000)
    asm.li(t1, 0xAAAA)
    asm.sw(t1, t0, 0)
    asm.li(t0, FERRY + 0x004)
    asm.li(t1, 0xBBBB)
    asm.sw(t1, t0, 0)
    asm.li(t0, FERRY + 0x040)
    asm.sw(x0, t0, 0)              # SRC = 0
    asm.li(t0, FERRY + 0x044)
    asm.addi(t1, x0, 8)
    asm.sw(t1, t0, 0)              # DST = 8
    asm.li(t0, FERRY + 0x048)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # COUNT = 2
    asm.li(t0, FERRY + 0x04C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # start
    asm.li(t2, 30)
    asm.label("f_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "f_w")
    asm.li(t0, FERRY + 0x020)
    asm.lw(s0, t0, 0)              # scratch[8] should be 0xAAAA
    print_label(asm, "FERRY", s0)

    # ARBOR: clear, raise sources 3 and 7, mask all in, claim
    asm.li(t0, ARBOR + 0x010)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # clear
    asm.li(t0, ARBOR + 0x014)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)              # raise 3
    asm.addi(t1, x0, 7)
    asm.sw(t1, t0, 0)              # raise 7
    asm.li(t0, ARBOR + 0x004)
    asm.li(t1, 0xFFFF)
    asm.sw(t1, t0, 0)              # mask all in
    asm.li(t0, ARBOR + 0x008)
    asm.lw(s0, t0, 0)              # claim — should return 7
    print_label(asm, "ARBOR", s0)

    # PYLON: clear, push 3 values, pop 3 values
    asm.li(t0, PYLON + 0x014)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # clear
    asm.li(t0, PYLON + 0x000)
    asm.li(t1, 0x1111)
    asm.sw(t1, t0, 0)
    asm.li(t1, 0x2222)
    asm.sw(t1, t0, 0)
    asm.li(t1, 0x3333)
    asm.sw(t1, t0, 0)
    asm.li(t0, PYLON + 0x010)
    asm.lw(s0, t0, 0)              # count = 3
    print_label(asm, "PYLON", s0)

    # DRUM: program OUT 0x42, OUT 0x43, HALT; run; read OUTPUT
    asm.li(t0, DRUM + 0x04C)
    asm.addi(t1, x0, 2)
    asm.sw(t1, t0, 0)              # reset
    asm.li(t0, DRUM + 0x000)
    asm.li(t1, (1 << 28) | 0x42)
    asm.sw(t1, t0, 0)
    asm.li(t0, DRUM + 0x004)
    asm.li(t1, (1 << 28) | 0x43)
    asm.sw(t1, t0, 0)
    asm.li(t0, DRUM + 0x008)
    asm.li(t1, 4 << 28)
    asm.sw(t1, t0, 0)              # HALT
    asm.li(t0, DRUM + 0x04C)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)              # start
    asm.li(t2, 30)
    asm.label("d_w")
    asm.addi(t2, t2, -1)
    asm.bne(t2, x0, "d_w")
    asm.li(t0, DRUM + 0x040)
    asm.lw(s0, t0, 0)              # OUTPUT = 0x43
    print_label(asm, "DRUM", s0)

    for ch in "PERIPHERAL:DONE":
        asm.addi(a0, x0, ord(ch))
        asm.call("putc")
    asm.addi(a0, x0, 10)
    asm.call("putc")

    asm.li(t0, 0x100000)
    asm.label("_final_delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "_final_delay")
    asm.j("main")

    asm.resolve()
    return asm.code


def predict():
    return {
        "CLASPA1": 0,           # acquire slot 0 returns 0 (was free)
        "CLASPA2": 0,           # acquire slot 1 returns 0 (was free)
        "CLASPST": 3,           # both slots 0 and 1 set
        "GPIO":    0x55AA,      # output drives this value
        "PULSE":   None,        # counter is timing-dependent
        "SPOKE":   None,        # status timing-dependent
        "WIRE":    None,        # FSM state timing-dependent
        "FERRY":   0xAAAA,      # scratch[8] after copy
        "ARBOR":   7,           # priority encoder picks highest
        "PYLON":   3,           # 3 entries pushed
        "DRUM":    0x43,        # last OUT value before HALT
    }


def main():
    firmware = generate_firmware()
    print(f"Peripheral firmware: {len(firmware)} instructions ({len(firmware)*4} bytes)")
    print(f"BRAM usage: {len(firmware)}/1024 ({len(firmware)*100//1024}%)")
    expected = predict()
    print("Expected:")
    for label, val in expected.items():
        if val is None:
            print(f"  {label:8s}: variable")
        else:
            print(f"  {label:8s}: 0x{val:08X}")
    if "--gen-only" in sys.argv:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
