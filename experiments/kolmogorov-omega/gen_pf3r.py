#!/usr/bin/env python3
"""Minimal prefix-free Omega experiment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "modules" / "rime-i"))
from gen_firmware import RV32I

x0, ra, sp = 0, 1, 2
t0, t1, t2, t3 = 5, 6, 7, 28
a0, a1 = 10, 11
s0, s1, s2, s3, s4, s5, s6, s7 = 8, 9, 18, 19, 20, 21, 22, 23
UART = 0x20000000
MOD_PF  = 0x30000000
MOD_PFB = 0x31000000

def build():
    a = RV32I()
    a.lui(sp, 0x00001); a.lui(s5, UART >> 12); a.j("main")

    a.label("putc"); a.lw(t0,s5,4); a.bne(t0,x0,"putc"); a.sw(a0,s5,0); a.ret()
    a.label("puthex"); a.addi(sp,sp,-8); a.sw(ra,sp,4); a.sw(s0,sp,0)
    a.mv(s0,a0); a.addi(s1,x0,28)
    a.label("ph_l"); a.blt(s1,x0,"ph_x")
    a.srl(a0,s0,s1); a.andi(a0,a0,0xF); a.addi(t0,x0,10)
    a.blt(a0,t0,"ph_d"); a.addi(a0,a0,55); a.j("ph_e")
    a.label("ph_d"); a.addi(a0,a0,48)
    a.label("ph_e"); a.call("putc"); a.addi(s1,s1,-4); a.j("ph_l")
    a.label("ph_x"); a.lw(s0,sp,0); a.lw(ra,sp,4); a.addi(sp,sp,8); a.ret()

    a.label("main")
    for ch in "GO\r\n": a.addi(a0,x0,ord(ch)); a.call("putc")

    # Single search: PF, length 6, target 0
    a.lui(s6, MOD_PF >> 12)
    a.addi(t0, x0, 6); a.sw(t0, s6, 0x2C)  # SEARCH_LEN=6
    a.addi(t0, x0, 0); a.sw(t0, s6, 0x1C)  # INIT_A=0
    a.addi(t0, x0, 0); a.sw(t0, s6, 0x20)  # INIT_B=0
    a.addi(t0, x0, 0); a.sw(t0, s6, 0x00)  # TARGET=0
    a.addi(t0, x0, 1); a.sw(t0, s6, 0x04)  # START

    # Poll
    a.label("w1")
    a.lw(t0, s6, 0x08); a.andi(t0, t0, 1)
    a.bne(t0, x0, "w1")

    # Print halt count
    for ch in "H:": a.addi(a0,x0,ord(ch)); a.call("putc")
    a.lw(a0, s6, 0x34); a.call("puthex")
    a.addi(a0,x0,10); a.call("putc")

    # Print progs tried
    for ch in "P:": a.addi(a0,x0,ord(ch)); a.call("putc")
    a.lw(a0, s6, 0x28); a.call("puthex")
    a.addi(a0,x0,10); a.call("putc")

    for ch in "DONE\r\n": a.addi(a0,x0,ord(ch)); a.call("putc")
    a.li(t0, 0x200000); a.label("_d"); a.addi(t0,t0,-1); a.bne(t0,x0,"_d"); a.j("main")
    a.resolve()
    return a.code

if __name__ == "__main__":
    fw = build()
    print(f"Firmware: {len(fw)} instructions")
    out = Path(__file__).resolve().parent
    with open(out / "firmware.hex", "w") as f:
        for i in range(1024):
            f.write(f"{fw[i] if i < len(fw) else 0x13:08x}\n")
