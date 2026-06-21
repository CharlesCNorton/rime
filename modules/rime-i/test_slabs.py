#!/usr/bin/env python3
"""Test RIME-I at every slab count from 1 to max on silicon.

Each test generates firmware that fills an array spanning nearly all
available RAM, verifies it, prints PASS or FAIL, then LOOPS so the
output survives the JTAG-to-UART driver switch.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent.parent
_mod = Path(__file__).resolve().parent
sys.path.insert(0, str(_repo))

TOTAL_LUTS = 24288
MARGIN_PCT = 20


def lui(rd, imm): return ((imm & 0xFFFFF) << 12) | (rd << 7) | 0x37
def addi(rd, rs, imm): return ((imm & 0xFFF) << 20) | (rs << 15) | (rd << 7) | 0x13
def add(rd, a, b): return (b << 20) | (a << 15) | (rd << 7) | 0x33
def slli(rd, rs, sh): return (sh << 20) | (rs << 15) | (1 << 12) | (rd << 7) | 0x13
def sw(rs2, rs1, imm):
    return ((imm >> 5 & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | ((imm & 0x1F) << 7) | 0x23
def lw(rd, rs, imm): return ((imm & 0xFFF) << 20) | (rs << 15) | (2 << 12) | (rd << 7) | 0x03
def bne_off(rs1, rs2, off):
    return ((off >> 12 & 1) << 31) | ((off >> 5 & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | (1 << 12) | ((off >> 1 & 0xF) << 8) | ((off >> 11 & 1) << 7) | 0x63
def bge_off(rs1, rs2, off):
    return ((off >> 12 & 1) << 31) | ((off >> 5 & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | (5 << 12) | ((off >> 1 & 0xF) << 8) | ((off >> 11 & 1) << 7) | 0x63
def jal_off(rd, off):
    return ((off >> 20 & 1) << 31) | ((off >> 1 & 0x3FF) << 21) | ((off >> 11 & 1) << 20) | ((off >> 12 & 0xFF) << 12) | (rd << 7) | 0x6F
def jalr(rd, rs, imm): return ((imm & 0xFFF) << 20) | (rs << 15) | (rd << 7) | 0x67

x0, ra, sp, t0, t1, t2, a0, s0, s1, s2, s3, s4 = 0, 1, 2, 5, 6, 7, 10, 8, 9, 18, 19, 20


def li(rd, val):
    """Load immediate into rd. Returns list of 1 or 2 instructions."""
    val = val & 0xFFFFFFFF
    sv = val if val < 0x80000000 else val - 0x100000000
    if -2048 <= sv <= 2047:
        return [addi(rd, x0, val & 0xFFF)]
    upper = (val + 0x800) >> 12
    lower = val & 0xFFF
    if lower >= 0x800:
        lower -= 0x1000
    result = [lui(rd, upper & 0xFFFFF)]
    if lower != 0:
        result.append(addi(rd, rd, lower & 0xFFF))
    return result


def gen_slab_firmware(mem_words):
    """Generate looping firmware that fills and verifies memory."""
    code_reserve = 80
    stack_reserve = 32
    array_words = mem_words - code_reserve - stack_reserve
    if array_words < 8:
        array_words = 8
    array_base = code_reserve * 4
    stack_top = mem_words * 4

    c = []

    # Setup
    c.extend(li(sp, stack_top))
    c.append(lui(s4, 0x20000))

    # Jump over putc
    j_main_idx = len(c)
    c.append(0)  # placeholder

    # putc: write a0 to UART with busy-wait
    putc_idx = len(c)
    c.append(lw(t0, s4, 4))
    c.append(bne_off(t0, x0, -4))
    c.append(sw(a0, s4, 0))
    c.append(jalr(0, ra, 0))

    # main (loops forever)
    main_idx = len(c)
    c[j_main_idx] = jal_off(0, (main_idx - j_main_idx) * 4)

    # li s0, array_base
    c.extend(li(s0, array_base))
    # li s1, array_words
    c.extend(li(s1, array_words))
    # s2 = 0 (index)
    c.append(addi(s2, x0, 0))

    # Fill: array[i] = i*37 + 0xA5
    fill_idx = len(c)
    c.append(bge_off(s2, s1, 0))  # placeholder
    c.append(slli(t0, s2, 5))     # *32
    c.append(slli(t1, s2, 2))     # *4
    c.append(add(t0, t0, t1))     # *36
    c.append(add(t0, t0, s2))     # *37
    c.append(addi(t0, t0, 165))   # +0xA5
    c.append(slli(t1, s2, 2))
    c.append(add(t1, t1, s0))
    c.append(sw(t0, t1, 0))
    c.append(addi(s2, s2, 1))
    c.append(jal_off(0, (fill_idx - len(c)) * 4))
    fill_done_idx = len(c)
    c[fill_idx] = bge_off(s2, s1, (fill_done_idx - fill_idx) * 4)

    # Verify
    c.append(addi(s2, x0, 0))
    c.append(addi(s3, x0, 0))  # errors

    check_idx = len(c)
    c.append(bge_off(s2, s1, 0))  # placeholder
    c.append(slli(t0, s2, 5))
    c.append(slli(t1, s2, 2))
    c.append(add(t0, t0, t1))
    c.append(add(t0, t0, s2))
    c.append(addi(t0, t0, 165))
    c.append(slli(t1, s2, 2))
    c.append(add(t1, t1, s0))
    c.append(lw(t2, t1, 0))
    # if mismatch, increment error count
    match_idx = len(c)
    c.append(bne_off(t0, t2, 0))  # placeholder -> mismatch
    c.append(jal_off(0, 0))       # placeholder -> next
    mismatch_idx = len(c)
    c[match_idx] = bne_off(t0, t2, (mismatch_idx - match_idx) * 4)
    c.append(addi(s3, s3, 1))
    next_idx = len(c)
    c[match_idx + 1] = jal_off(0, (next_idx - (match_idx + 1)) * 4)
    c.append(addi(s2, s2, 1))
    c.append(jal_off(0, (check_idx - len(c)) * 4))
    check_done_idx = len(c)
    c[check_idx] = bge_off(s2, s1, (check_done_idx - check_idx) * 4)

    # Print PASS or FAIL
    fail_branch_idx = len(c)
    c.append(bne_off(s3, x0, 0))  # placeholder -> fail

    for ch in "PASS\n":
        c.append(addi(a0, x0, ord(ch)))
        c.append(jal_off(ra, (putc_idx - len(c)) * 4))

    # Delay then loop back to main
    c.append(lui(t1, 500))        # ~2M iterations delay
    c.append(addi(t1, t1, -1))
    c.append(bne_off(t1, x0, -4))
    c.append(jal_off(0, (main_idx - len(c)) * 4))

    fail_idx = len(c)
    c[fail_branch_idx] = bne_off(s3, x0, (fail_idx - fail_branch_idx) * 4)

    for ch in "FAIL\n":
        c.append(addi(a0, x0, ord(ch)))
        c.append(jal_off(ra, (putc_idx - len(c)) * 4))

    # Delay + loop
    c.append(lui(t1, 500))
    c.append(addi(t1, t1, -1))
    c.append(bne_off(t1, x0, -4))
    c.append(jal_off(0, (main_idx - len(c)) * 4))

    return c, array_words


def patch_and_build(mem_words, code):
    top = _mod / "rime_i_top.sv"
    text = top.read_text()
    text = re.sub(r'parameter integer MEM_WORDS = \d+', f'parameter integer MEM_WORDS = {mem_words}', text)
    s = text.index("    initial begin")
    e = text.index("    end", s) + len("    end")
    init = ["    initial begin"]
    init.append("        integer _i;")
    init.append("        for (_i = 0; _i < MEM_WORDS; _i = _i + 1)")
    init.append("            bram[_i] = 32'h00000013;")
    for i, w in enumerate(code):
        init.append(f"        bram[{i}] = 32'h{w:08x};")
    init.append("    end")
    text = text[:s] + "\n".join(init) + text[e:]
    top.write_text(text)

    result = subprocess.run(
        [sys.executable, str(_repo / "icepi_helper.py"), "build", "rime-i", "--clean"],
        capture_output=True, text=True, cwd=str(_repo), timeout=300,
    )
    luts = 0
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if "Total LUT4s:" in line:
            luts = int(line.split("LUT4s:")[1].split("/")[0].strip())
    return result.returncode == 0, luts


def flash_and_read():
    from icepi_admin import (_pnputil_switch_to_jtag, _pnputil_switch_to_uart,
                             probe_jtag_target, run_loader_command)
    _pnputil_switch_to_jtag()
    time.sleep(3)
    for _ in range(6):
        if probe_jtag_target():
            break
        time.sleep(2)
    run_loader_command(["-b", "icepi-zero", str(_mod / "bitstream.bit")], check=True)
    _pnputil_switch_to_uart()
    time.sleep(5)

    import serial.tools.list_ports
    import serial
    port = next((p.device for p in serial.tools.list_ports.comports()
                 if "0403" in (p.hwid or "")), None)
    if not port:
        return ""
    with serial.Serial(port, 115200, timeout=15) as ser:
        return ser.read(100).decode("ascii", errors="replace").strip()


def main():
    margin_luts = int(TOTAL_LUTS * MARGIN_PCT / 100)
    max_luts = TOTAL_LUTS - margin_luts
    print(f"Total: {TOTAL_LUTS} LUTs | {MARGIN_PCT}% margin = {margin_luts} reserved | max usable: {max_luts}")
    print()

    results = []
    for slabs in range(1, 20):
        mem_words = slabs * 256
        code, array_words = gen_slab_firmware(mem_words)

        if len(code) > mem_words:
            print(f"{slabs:2d} KB: code ({len(code)} words) > memory ({mem_words} words), skipping")
            continue

        print(f"--- {slabs} slab(s) = {slabs} KB | {mem_words} words | array {array_words}w = {array_words*4} bytes ---")

        ok, luts = patch_and_build(mem_words, code)
        if not ok:
            print("  BUILD FAILED")
            results.append((slabs, False, 0, "build failed"))
            break

        if luts > max_luts:
            print(f"  {luts} LUTs ({luts*100//TOTAL_LUTS}%) exceeds {MARGIN_PCT}% margin ({max_luts} max)")
            results.append((slabs, False, luts, "over margin"))
            break

        output = flash_and_read()
        passed = "PASS" in output
        status = "PASS" if passed else "FAIL"
        remaining_pct = (TOTAL_LUTS - luts) * 100 // TOTAL_LUTS
        print(f"  [{status}] {luts} LUTs ({luts*100//TOTAL_LUTS}%) | {remaining_pct}% free | {output[:40]!r}")
        results.append((slabs, passed, luts, output[:40]))

        if not passed:
            break

    print()
    print("=" * 60)
    print("SLAB TEST RESULTS")
    print("=" * 60)
    for n, passed, luts, msg in results:
        pct = luts * 100 // TOTAL_LUTS if luts else 0
        free = (TOTAL_LUTS - luts) * 100 // TOTAL_LUTS if luts else 0
        print(f"  {n:2d} slab(s) = {n:2d} KB: {'PASS' if passed else 'FAIL':4s} | {luts:5d} LUTs ({pct:2d}%) | {free:2d}% free")
    print("=" * 60)

    # Restore RIME service
    print("\nRestoring RIME service...")
    from icepi_admin import (_pnputil_switch_to_jtag, _pnputil_switch_to_uart,
                             probe_jtag_target, run_loader_command)
    _pnputil_switch_to_jtag()
    time.sleep(3)
    for _ in range(6):
        if probe_jtag_target():
            break
        time.sleep(2)
    run_loader_command(["-b", "icepi-zero", "-r"], check=True)
    _pnputil_switch_to_uart()
    time.sleep(3)
    print("RIME service restored.")


if __name__ == "__main__":
    main()
