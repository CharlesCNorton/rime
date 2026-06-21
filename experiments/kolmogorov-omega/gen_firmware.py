#!/usr/bin/env python3
"""Generate firmware for Experiment 25: Kolmogorov/Solomonoff/Omega.

Sweeps all 256 target values through the 200-interpreter KOLMOGOROV module.
For each target: start search, wait for completion, read K(target), match_count,
halt_count, progs_tried. Print results as labelled hex over UART.

At the end, halt_count / progs_tried = Omega (halting fraction).
match_count / halt_count = P(target) (algorithmic probability of target).
K(target) = length of shortest program producing target.
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
MOD_A = 0x30000000  # ISA-A
MOD_2 = 0x31000000  # ISA-B (reusing slot)
MOD_3 = 0x32000000  # unused this run

# KOLMOGOROV register map:
# 0x000: TARGET (write)
# 0x004: CONTROL (write) — bit 0 = start search
# 0x008: STATUS (read) — bit 0 = busy, bit 1 = k_found, bit 2 = run_done
# 0x00C: K_VALUE (read)
# 0x010: K_PROGRAM (read)
# 0x024: BATCH_NUM (read)
# 0x028: PROGS_TRIED (read)
# 0x02C: SEARCH_LEN (write/read)
# 0x030: MATCH_COUNT (read)
# 0x034: HALT_COUNT (read)

def build():
    a = RV32I()
    a.lui(sp, 0x00001)
    a.lui(s5, UART >> 12)
    a.j("main")

    # putc
    a.label("putc")
    a.lw(t0, s5, 4); a.bne(t0, x0, "putc"); a.sw(a0, s5, 0); a.ret()

    # puthex
    a.label("puthex")
    a.addi(sp, sp, -8); a.sw(ra, sp, 4); a.sw(s0, sp, 0)
    a.mv(s0, a0); a.addi(s1, x0, 28)
    a.label("ph_l"); a.blt(s1, x0, "ph_x")
    a.srl(a0, s0, s1); a.andi(a0, a0, 0xF); a.addi(t0, x0, 10)
    a.blt(a0, t0, "ph_d"); a.addi(a0, a0, 55); a.j("ph_e")
    a.label("ph_d"); a.addi(a0, a0, 48)
    a.label("ph_e"); a.call("putc"); a.addi(s1, s1, -4); a.j("ph_l")
    a.label("ph_x"); a.lw(s0, sp, 0); a.lw(ra, sp, 4); a.addi(sp, sp, 8); a.ret()

    # put2hex: print a0 as 2-digit hex
    a.label("put2hex")
    a.addi(sp, sp, -8); a.sw(ra, sp, 4); a.sw(s0, sp, 0)
    a.mv(s0, a0)
    a.srli(a0, s0, 4); a.andi(a0, a0, 0xF); a.addi(t0, x0, 10)
    a.blt(a0, t0, "p2d1"); a.addi(a0, a0, 55); a.j("p2e1")
    a.label("p2d1"); a.addi(a0, a0, 48)
    a.label("p2e1"); a.call("putc")
    a.andi(a0, s0, 0xF); a.addi(t0, x0, 10)
    a.blt(a0, t0, "p2d2"); a.addi(a0, a0, 55); a.j("p2e2")
    a.label("p2d2"); a.addi(a0, a0, 48)
    a.label("p2e2"); a.call("putc")
    a.lw(s0, sp, 0); a.lw(ra, sp, 4); a.addi(sp, sp, 8); a.ret()

    a.label("main")

    # Banner
    for ch in "EXP25:DUAL\r\n":
        a.addi(a0, x0, ord(ch)); a.call("putc")

    # Sweep lengths 1-8, target 0, for BOTH ISAs — Omega convergence comparison
    a.addi(s3, x0, 1)   # length = 1
    a.label("len_loop")
    a.addi(t0, x0, 9)
    a.bge(s3, t0, "len_done")

    # ISA-A
    a.lui(s6, MOD_A >> 12)
    a.sw(s3, s6, 0x2C)
    a.addi(t0, x0, 0); a.sw(t0, s6, 0x00)
    a.addi(t0, x0, 1); a.sw(t0, s6, 0x04)
    a.label("wa")
    a.lw(t0, s6, 0x08); a.andi(t0, t0, 1); a.bne(t0, x0, "wa")

    # ISA-B
    a.lui(s4, MOD_F >> 12)
    a.sw(s3, s4, 0x2C)
    a.addi(t0, x0, 0); a.sw(t0, s4, 0x00)
    a.addi(t0, x0, 1); a.sw(t0, s4, 0x04)
    a.label("wb")
    a.lw(t0, s4, 0x08); a.andi(t0, t0, 1); a.bne(t0, x0, "wb")

    # ISA-C
    a.lui(s2, MOD_G >> 12)
    a.sw(s3, s2, 0x2C)
    a.addi(t0, x0, 0); a.sw(t0, s2, 0x00)
    a.addi(t0, x0, 1); a.sw(t0, s2, 0x04)
    a.label("wc")
    a.lw(t0, s2, 0x08); a.andi(t0, t0, 1); a.bne(t0, x0, "wc")

    # Print: "L:X A:HHHH B:HHHH C:HHHH P:PPPP\n"
    a.addi(a0, x0, ord('L')); a.call("putc")
    a.mv(a0, s3); a.call("put2hex")
    a.addi(a0, x0, ord(' ')); a.call("putc")
    a.addi(a0, x0, ord('A')); a.call("putc")
    a.lw(a0, s6, 0x34); a.call("puthex")
    a.addi(a0, x0, ord(' ')); a.call("putc")
    a.addi(a0, x0, ord('F')); a.call("putc")
    a.lw(a0, s4, 0x34); a.call("puthex")
    a.addi(a0, x0, ord(' ')); a.call("putc")
    a.addi(a0, x0, ord('G')); a.call("putc")
    a.lw(a0, s2, 0x34); a.call("puthex")
    a.addi(a0, x0, ord(' ')); a.call("putc")
    a.addi(a0, x0, ord('P')); a.call("putc")
    a.lw(a0, s6, 0x28); a.call("puthex")
    a.addi(a0, x0, 10); a.call("putc")

    a.addi(s3, s3, 1)
    a.j("len_loop")
    a.label("len_done")

    # Skip the full 256-target sweep to save time — Omega convergence is the goal
    a.j("sweep_done")

    # (Dead code — target sweep placeholder)
    a.lui(s6, MOD_A >> 12)
    a.addi(t0, x0, 6); a.sw(t0, s6, 0x2C)
    a.addi(s7, x0, 0)
    a.label("target_loop")
    a.li(t0, 256)
    a.bge(s7, t0, "sweep_done")

    # Set target (ISA-A only for per-target sweep)
    a.lui(s6, MOD_A >> 12)
    a.sw(s7, s6, 0x00)
    a.addi(t0, x0, 1)
    a.sw(t0, s6, 0x04)

    # Wait for search to complete (STATUS bit 0 = busy → poll until 0)
    a.label("wait_search")
    a.lw(t0, s6, 0x08)  # STATUS
    a.andi(t0, t0, 1)   # bit 0 = busy
    a.bne(t0, x0, "wait_search")

    # Read results
    # Print: "T:XX K:V M:MMMM H:HHHH\n"
    # T = target (2 hex digits)
    a.addi(a0, x0, ord('T')); a.call("putc")
    a.mv(a0, s7); a.call("put2hex")
    a.addi(a0, x0, ord(' ')); a.call("putc")

    # K value
    a.addi(a0, x0, ord('K')); a.call("putc")
    a.lw(t0, s6, 0x08)  # STATUS
    a.andi(t1, t0, 2)   # bit 1 = k_found
    a.bne(t1, x0, "k_found")
    a.addi(a0, x0, ord('-')); a.call("putc")  # no K found
    a.j("k_done")
    a.label("k_found")
    a.lw(a0, s6, 0x0C)  # K_VALUE
    a.call("put2hex")
    a.label("k_done")
    a.addi(a0, x0, ord(' ')); a.call("putc")

    # Match count
    a.addi(a0, x0, ord('M')); a.call("putc")
    a.lw(a0, s6, 0x30)  # MATCH_COUNT
    a.call("puthex")
    a.addi(a0, x0, ord(' ')); a.call("putc")

    # Halt count
    a.addi(a0, x0, ord('H')); a.call("putc")
    a.lw(a0, s6, 0x34)  # HALT_COUNT
    a.call("puthex")

    a.addi(a0, x0, 10); a.call("putc")  # newline

    # Next target
    a.addi(s7, s7, 1)
    a.j("target_loop")

    a.label("sweep_done")
    # Print total progs tried and final halt count
    for ch in "TOTAL:":
        a.addi(a0, x0, ord(ch)); a.call("putc")
    # We need a final run to get the totals — they reset each target.
    # Actually, let's just read the last values (they represent the last target's search).
    # For Omega, we need the cumulative halt_count across ALL searches.
    # The current design resets counters on each search start.
    # For the full Omega, we'd need to accumulate in firmware.
    # For now: print per-target data and compute Omega in the host.
    for ch in "DONE\r\n":
        a.addi(a0, x0, ord(ch)); a.call("putc")

    # Delay and loop
    a.li(t0, 0x200000)
    a.label("_d"); a.addi(t0, t0, -1); a.bne(t0, x0, "_d")
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
    print(f"Wrote firmware.hex")
