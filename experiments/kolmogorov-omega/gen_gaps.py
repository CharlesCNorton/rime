#!/usr/bin/env python3
"""Generate firmware for Gap 2 (lengths 9-12) and Gap 5 (initial state sweep).

Uses two KOLMOGOROV modules: ISA-A at 0x30, ISA-B at 0x31.

Phase 1 (Gap 5): sweep init_a across {0,1,42,127,128,255} at length 6.
  For each init_a, run both ISAs, print halt counts.
  If Omega is init-independent, all init_a values give the same result.

Phase 2 (Gap 2): extend ISA-A and ISA-B to lengths 9, 10, 11, 12.
  Length 9: 10,077,696 programs. At 16 interps/batch: 629,856 batches.
  At 260 cycles/batch: ~164M cycles = 6.5 seconds per ISA.
  Length 10: 60,466,176 programs = ~39 seconds.
  Length 11: 362,797,056 = ~235 seconds (~4 min).
  Length 12: 2,176,782,336 = too long. Stop at 11.
"""
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
MOD_A = 0x30000000
MOD_B = 0x31000000

# KOLMOGOROV registers:
# 0x000: TARGET, 0x004: CONTROL, 0x008: STATUS, 0x00C: K_VALUE
# 0x01C: INIT_A, 0x020: INIT_B, 0x028: PROGS_TRIED
# 0x02C: SEARCH_LEN, 0x034: HALT_COUNT

def build():
    a = RV32I()
    a.lui(sp, 0x00001)
    a.lui(s5, UART >> 12)
    a.j("main")

    # putc
    a.label("putc"); a.lw(t0,s5,4); a.bne(t0,x0,"putc"); a.sw(a0,s5,0); a.ret()

    # puthex
    a.label("puthex"); a.addi(sp,sp,-8); a.sw(ra,sp,4); a.sw(s0,sp,0)
    a.mv(s0,a0); a.addi(s1,x0,28)
    a.label("ph_l"); a.blt(s1,x0,"ph_x")
    a.srl(a0,s0,s1); a.andi(a0,a0,0xF); a.addi(t0,x0,10)
    a.blt(a0,t0,"ph_d"); a.addi(a0,a0,55); a.j("ph_e")
    a.label("ph_d"); a.addi(a0,a0,48)
    a.label("ph_e"); a.call("putc"); a.addi(s1,s1,-4); a.j("ph_l")
    a.label("ph_x"); a.lw(s0,sp,0); a.lw(ra,sp,4); a.addi(sp,sp,8); a.ret()

    # put2hex
    a.label("put2hex"); a.addi(sp,sp,-8); a.sw(ra,sp,4); a.sw(s0,sp,0)
    a.mv(s0,a0)
    a.srli(a0,s0,4); a.andi(a0,a0,0xF); a.addi(t0,x0,10)
    a.blt(a0,t0,"p2d1"); a.addi(a0,a0,55); a.j("p2e1")
    a.label("p2d1"); a.addi(a0,a0,48)
    a.label("p2e1"); a.call("putc")
    a.andi(a0,s0,0xF); a.addi(t0,x0,10)
    a.blt(a0,t0,"p2d2"); a.addi(a0,a0,55); a.j("p2e2")
    a.label("p2d2"); a.addi(a0,a0,48)
    a.label("p2e2"); a.call("putc")
    a.lw(s0,sp,0); a.lw(ra,sp,4); a.addi(sp,sp,8); a.ret()

    # run_search(s6=module base, s3=length, s7=init_a): run and print "H:haltcount P:progs"
    a.label("run_search")
    a.addi(sp,sp,-4); a.sw(ra,sp,0)
    a.sw(s3, s6, 0x2C)          # SEARCH_LEN
    a.sw(s7, s6, 0x1C)          # INIT_A
    a.addi(t0,x0,0); a.sw(t0,s6,0x20)  # INIT_B = 0
    a.addi(t0,x0,0); a.sw(t0,s6,0x00)  # TARGET = 0
    a.addi(t0,x0,1); a.sw(t0,s6,0x04)  # START
    a.label("rs_w")
    a.lw(t0,s6,0x08); a.andi(t0,t0,1); a.bne(t0,x0,"rs_w")
    a.lw(a0,s6,0x34); a.call("puthex")   # halt count
    a.addi(a0,x0,ord(' ')); a.call("putc")
    a.lw(a0,s6,0x28); a.call("puthex")   # progs tried
    a.lw(ra,sp,0); a.addi(sp,sp,4); a.ret()

    a.label("main")

    # ===== GAP 5: init_a sweep at length 6 =====
    for ch in "GAP5\r\n": a.addi(a0,x0,ord(ch)); a.call("putc")

    # init_a values to test: 0, 1, 42, 127, 128, 255
    init_vals = [0, 1, 42, 127, 128, 255]
    for iv in init_vals:
        a.addi(s3, x0, 6)       # length = 6
        a.li(s7, iv)             # init_a

        # Print "I:XX A:"
        a.addi(a0,x0,ord('I')); a.call("putc")
        a.mv(a0,s7); a.call("put2hex")
        a.addi(a0,x0,ord(' ')); a.call("putc")
        a.addi(a0,x0,ord('A')); a.call("putc")

        # Run ISA-A
        a.lui(s6, MOD_A >> 12)
        a.call("run_search")

        # Print " B:"
        a.addi(a0,x0,ord(' ')); a.call("putc")
        a.addi(a0,x0,ord('B')); a.call("putc")

        # Run ISA-B
        a.lui(s6, MOD_B >> 12)
        a.call("run_search")

        a.addi(a0,x0,10); a.call("putc")

    # ===== GAP 2: lengths 1-11, init_a=0 =====
    for ch in "GAP2\r\n": a.addi(a0,x0,ord(ch)); a.call("putc")

    a.addi(s7, x0, 0)           # init_a = 0

    a.addi(s3, x0, 1)           # length = 1
    a.label("g2_loop")
    a.addi(t0, x0, 12)          # up to length 11
    a.bge(s3, t0, "g2_done")

    a.addi(a0,x0,ord('L')); a.call("putc")
    a.mv(a0,s3); a.call("put2hex")
    a.addi(a0,x0,ord(' ')); a.call("putc")
    a.addi(a0,x0,ord('A')); a.call("putc")

    a.lui(s6, MOD_A >> 12)
    a.call("run_search")

    a.addi(a0,x0,ord(' ')); a.call("putc")
    a.addi(a0,x0,ord('B')); a.call("putc")

    a.lui(s6, MOD_B >> 12)
    a.call("run_search")

    a.addi(a0,x0,10); a.call("putc")

    a.addi(s3, s3, 1)
    a.j("g2_loop")

    a.label("g2_done")
    for ch in "DONE\r\n": a.addi(a0,x0,ord(ch)); a.call("putc")
    a.li(t0, 0x200000)
    a.label("_d"); a.addi(t0,t0,-1); a.bne(t0,x0,"_d")
    a.j("main")

    a.resolve()
    return a.code


if __name__ == "__main__":
    fw = build()
    print(f"Firmware: {len(fw)} instructions ({len(fw)*4} bytes)")
    out = Path(__file__).resolve().parent
    with open(out / "firmware.hex", "w") as f:
        for i in range(1024):
            w = fw[i] if i < len(fw) else 0x00000013
            f.write(f"{w:08x}\n")
    print("Wrote firmware.hex")
