#!/usr/bin/env python3
"""LACE basic silicon test — verify 2D and 3D interleave on hardware."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compositor_test import build_module, flash_and_read, restore_rime
from compositor_template import generate_top_sv
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rime-i"))
_gf_src = (Path(__file__).resolve().parent.parent / "rime-i" / "gen_firmware.py").read_text()
_gf_ns = {}
exec(_gf_src.split("\ndef generate_math_firmware")[0], _gf_ns)
RV32I = _gf_ns["RV32I"]

x0, ra, sp = 0, 1, 2
t0, t1, t2 = 5, 6, 7
a0, a1 = 10, 11
s0 = 8
UART = 0x20000000
MOD = 0x30000000


def gen_firmware():
    asm = RV32I()
    asm.lui(sp, 0x00001)
    asm.lui(s0, 0x20000)
    asm.j("main")

    asm.label("putc")
    asm.lw(t0, s0, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s0, 0)
    asm.ret()

    asm.label("puthex")
    asm.addi(sp, sp, -8)
    asm.sw(ra, sp, 4)
    asm.sw(a1, sp, 0)
    asm.mv(a1, a0)
    asm.addi(t2, x0, 28)
    asm.label("ph_loop")
    asm.blt(t2, x0, "ph_done")
    asm.srl(a0, a1, t2)
    asm.andi(a0, a0, 0xF)
    asm.addi(t0, x0, 10)
    asm.blt(a0, t0, "ph_dig")
    asm.addi(a0, a0, ord('A') - 10)
    asm.j("ph_em")
    asm.label("ph_dig")
    asm.addi(a0, a0, ord('0'))
    asm.label("ph_em")
    asm.call("putc")
    asm.addi(t2, t2, -4)
    asm.j("ph_loop")
    asm.label("ph_done")
    asm.lw(a1, sp, 0)
    asm.lw(ra, sp, 4)
    asm.addi(sp, sp, 8)
    asm.ret()

    asm.label("main")
    # Write X=1, Y=0, read Z2D_OUT (should be 1)
    asm.li(t0, MOD + 0x000)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)       # X2D = 1
    asm.li(t0, MOD + 0x004)
    asm.sw(x0, t0, 0)       # Y2D = 0
    asm.li(t0, MOD + 0x008)
    asm.lw(a0, t0, 0)       # read Z2D_OUT
    asm.call("puthex")
    asm.addi(a0, x0, 10)
    asm.call("putc")

    asm.label("done")
    asm.j("done")
    asm.resolve()
    return asm.code


def main():
    firmware = gen_firmware()
    mod_dir = Path(__file__).resolve().parent
    generate_top_sv("lace", firmware, mod_dir / "top.sv")
    if "--gen-only" in sys.argv:
        print(f"Generated {len(firmware)} instructions")
        return 0
    ok, luts = build_module("lace", firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return 1
    output = flash_and_read("lace")
    print(f"Output: {output!r}")
    restore_rime()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
