"""`trace` and `profile` commands: on-silicon observability for the rime-i
soft CPU via the snoop-tapped trace/profile instrumentation modules.

Both compose rime-i + one instrumentation module, run a firmware workload,
read the captured data back over UART, and render it on the host. They drive
the board through JTAG SRAM load + UART (the compositor flow), so run them
under `sg dialout` like the module tests.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from icepi.tools import REPO_ROOT

# The compositor build/flash/read flow and the RV32I assembler live in
# modules/; make them importable.
for _p in (str(REPO_ROOT), str(REPO_ROOT / "modules")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__all__ = ["cmd_trace", "cmd_profile"]


def _imports():
    from compositor_test import (  # type: ignore
        RV32I, build_module, flash_and_read, restore_rime,
        x0, ra, sp, t0, t1, t2, a0, s0, s1, s2, s3, s4, MOD_BASE, UART_BASE,
    )
    return dict(RV32I=RV32I, build_module=build_module, flash_and_read=flash_and_read,
                restore_rime=restore_rime, x0=x0, ra=ra, sp=sp, t0=t0, t1=t1, t2=t2,
                a0=a0, s0=s0, s1=s1, s2=s2, s3=s3, s4=s4,
                MOD_BASE=MOD_BASE, UART_BASE=UART_BASE)


# ---- shared firmware fragments ----

def _emit_io(a, R):
    x0, ra, sp, t0, a0, s0, s1, s4 = (R[k] for k in ("x0", "ra", "sp", "t0", "a0", "s0", "s1", "s4"))
    a.label("putc")
    a.lw(t0, s4, 4); a.bne(t0, x0, "putc"); a.sw(a0, s4, 0); a.ret()
    a.label("puthex")
    a.addi(sp, sp, -8); a.sw(ra, sp, 4); a.sw(s0, sp, 0)
    a.mv(s0, a0); a.addi(s1, x0, 28)
    a.label("ph_loop"); a.blt(s1, x0, "ph_done")
    a.srl(a0, s0, s1); a.andi(a0, a0, 0xF)
    a.addi(t0, x0, 10); a.blt(a0, t0, "ph_dig")
    a.addi(a0, a0, ord('A') - 10); a.j("ph_emit")
    a.label("ph_dig"); a.addi(a0, a0, ord('0'))
    a.label("ph_emit"); a.call("putc"); a.addi(s1, s1, -4); a.j("ph_loop")
    a.label("ph_done"); a.lw(s0, sp, 0); a.lw(ra, sp, 4); a.addi(sp, sp, 8); a.ret()


def _emit_line(a, R, text):
    x0, a0 = R["x0"], R["a0"]
    for ch in text:
        a.addi(a0, x0, ord(ch)); a.call("putc")
    a.addi(a0, x0, 10); a.call("putc")


def _emit_print_hex(a, R, value_reg):
    x0, a0 = R["x0"], R["a0"]
    a.mv(a0, value_reg); a.call("puthex")
    a.addi(a0, x0, 10); a.call("putc")


def _emit_print_reg(a, R, off):
    t0, a0, x0 = R["t0"], R["a0"], R["x0"]
    a.li(t0, R["MOD_BASE"] + off); a.lw(a0, t0, 0); a.call("puthex")
    a.addi(a0, x0, 10); a.call("putc")


# ---- profile ----

def _gen_profile_firmware(R, iters):
    a = R["RV32I"]()
    x0, sp, t0, t1, s2, s3, s4 = (R[k] for k in ("x0", "sp", "t0", "t1", "s2", "s3", "s4"))
    MOD, UART = R["MOD_BASE"], R["UART_BASE"]
    a.lui(sp, 0x00001); a.lui(s4, 0x20000); a.j("main")
    _emit_io(a, R)
    a.label("main")
    a.li(t0, MOD + 0x000); a.li(t1, 1); a.sw(t1, t0, 0)            # start
    # touch UART and module regions so every region counter is exercised
    a.li(t0, UART + 4)
    for _ in range(4):
        a.lw(t1, t0, 0)
    a.li(t0, MOD + 0x020)
    for _ in range(4):
        a.lw(t1, t0, 0)
    # compute workload (instruction fetches dominate)
    a.li(s2, iters); a.li(s3, 0)
    a.label("wl"); a.addi(s3, s3, 1); a.addi(s2, s2, -1); a.bne(s2, x0, "wl")
    a.li(t0, MOD + 0x000); a.li(t1, 2); a.sw(t1, t0, 0)            # stop
    _emit_line(a, R, "PROF")
    for off in (0x004, 0x008, 0x00C, 0x010, 0x014, 0x018, 0x01C):
        _emit_print_reg(a, R, off)
    _emit_line(a, R, "END")
    a.li(t0, 0x200000); a.label("pd"); a.addi(t0, t0, -1); a.bne(t0, x0, "pd"); a.j("main")
    a.resolve()
    return a.code


def _parse_profile(out):
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    keys = ["cycles", "txns", "reads", "writes", "bram", "uart", "mod"]
    for i, l in enumerate(lines):
        if l == "PROF" and i + 8 < len(lines) and lines[i + 8] == "END":
            try:
                vals = [int(lines[i + j], 16) for j in range(1, 8)]
            except ValueError:
                continue
            return dict(zip(keys, vals))
    return None


def _pct(n, d):
    return f"{(100.0 * n / d):.1f}%" if d else "—"


def _render_profile(p):
    cyc, txn = p["cycles"], p["txns"]
    lines = [
        "Execution profile (rime-i workload):",
        f"  cycles          : {cyc}",
        f"  transactions    : {txn}",
        f"    reads         : {p['reads']} ({_pct(p['reads'], txn)})",
        f"    writes        : {p['writes']} ({_pct(p['writes'], txn)})",
        "  by region:",
        f"    BRAM (code)   : {p['bram']} ({_pct(p['bram'], txn)})",
        f"    UART          : {p['uart']} ({_pct(p['uart'], txn)})",
        f"    module        : {p['mod']} ({_pct(p['mod'], txn)})",
        f"  bus utilization : {_pct(txn, cyc)} (txn/cycle)",
    ]
    return lines


def cmd_profile(args):
    R = _imports()
    iters = getattr(args, "iters", None) or 4000
    fw = _gen_profile_firmware(R, iters)
    print(f"profile: composing rime-i + profile ({len(fw)} instrs, {iters} workload iters)")
    ok, luts = R["build_module"]("profile", fw)
    if not ok:
        R["restore_rime"]()
        raise RuntimeError("profile composition build failed")
    print(f"built: {luts} LUTs; loading and running on silicon")
    out = R["flash_and_read"]("profile")
    R["restore_rime"]()
    p = _parse_profile(out)
    if p is None:
        raise RuntimeError(f"no profile block in board output: {out[:160]!r}")
    for line in _render_profile(p):
        print(line)
    return {"profile": p, "luts": luts, "iters": iters}


# ---- trace ----

def _gen_trace_firmware(R):
    a = R["RV32I"]()
    x0, sp, t0, t1, t2, s2, s3, s4, a0 = (R[k] for k in ("x0", "sp", "t0", "t1", "t2", "s2", "s3", "s4", "a0"))
    MOD = R["MOD_BASE"]
    a.lui(sp, 0x00001); a.lui(s4, 0x20000); a.j("main")
    _emit_io(a, R)
    a.label("main")
    a.li(t0, MOD + 0x000); a.li(t1, 1); a.sw(t1, t0, 0)           # arm
    # a few BRAM stores (writes) then a delay loop (fetches) fill the buffer
    a.li(t2, 0x100)
    a.li(t1, 0xA5); a.sw(t1, t2, 0)
    a.li(t1, 0x5A); a.sw(t1, t2, 4)
    a.li(t1, 0xC3); a.sw(t1, t2, 8)
    a.li(t1, 0x3C); a.sw(t1, t2, 12)
    a.li(t0, 200); a.label("twl"); a.addi(t0, t0, -1); a.bne(t0, x0, "twl")
    a.li(t0, MOD + 0x000); a.li(t1, 2); a.sw(t1, t0, 0)           # stop
    a.li(t0, MOD + 0x004); a.lw(s2, t0, 0)                        # count
    _emit_line(a, R, "TRC")
    _emit_print_hex(a, R, s2)
    # 8 entries at fixed offsets (unrolled; no computed offsets, which the
    # soft CPU mis-pipelined against back-to-back module reads).
    for k in range(8):
        a.li(t0, MOD + 0x010 + k * 8); a.lw(a0, t0, 0); a.call("puthex"); a.addi(a0, x0, 10); a.call("putc")  # ADDR[k]
        a.li(t0, MOD + 0x014 + k * 8); a.lw(a0, t0, 0); a.call("puthex"); a.addi(a0, x0, 10); a.call("putc")  # META[k]
    _emit_line(a, R, "END")
    a.li(t0, 0x200000); a.label("td"); a.addi(t0, t0, -1); a.bne(t0, x0, "td"); a.j("main")
    a.resolve()
    return a.code


def _parse_trace(out):
    # Values are fixed 8-hex-digit words framed by TRC..END. Concatenate the
    # hex between the markers and slice into 8-char words so an occasional
    # dropped UART newline (which merges two words on one line) can't misalign
    # the parse: count is the first word, then addr/meta pairs.
    lines = [l.strip() for l in out.splitlines()]
    hexset = set("0123456789abcdefABCDEF")
    for i, l in enumerate(lines):
        if l != "TRC":
            continue
        try:
            end = lines.index("END", i + 1)
        except ValueError:
            continue
        body = "".join(lines[i + 1:end])
        if not body or len(body) % 8 != 0 or any(c not in hexset for c in body):
            continue
        words = [body[j:j + 8] for j in range(0, len(body), 8)]
        count = int(words[0], 16)
        if count <= 0 or len(words) < 1 + 2 * count:
            continue
        return [(int(words[1 + 2 * k], 16), int(words[2 + 2 * k], 16)) for k in range(count)]
    return None


def _region(addr):
    return {0x0: "bram", 0x2: "uart", 0x3: "mod"}.get((addr >> 28) & 0xF, "?")


def _render_trace(entries, vcd_path):
    base_ts = min(m >> 4 for _, m in entries)
    reads = sum(1 for _, m in entries if (m & 0xF) == 0)
    writes = len(entries) - reads
    span = (entries[-1][1] >> 4) - base_ts
    lines = [
        f"Bus trace (rime-i, {len(entries)} transactions, span {span} cycles, "
        f"{reads} reads / {writes} writes):",
        f"  {'idx':>3}  {'t':>5}  {'addr':<10}  rw  wstrb  region",
        "  " + "-" * 44,
    ]
    shown = entries[:40]
    for idx, (addr, meta) in enumerate(shown):
        ts = (meta >> 4) - base_ts
        wstrb = meta & 0xF
        rw = "W" if wstrb else "R"
        lines.append(f"  {idx:>3}  {ts:>5}  0x{addr:08X}  {rw}   {wstrb:X}     {_region(addr)}")
    if len(entries) > len(shown):
        lines.append(f"  ... ({len(entries) - len(shown)} more; full capture in the VCD)")
    if vcd_path:
        _write_vcd(entries, vcd_path)
        lines.append(f"  VCD: {vcd_path}")
    return lines


def _write_vcd(entries, path):
    out = [
        "$comment RIME bus trace $end",
        "$timescale 1 ns $end",
        "$scope module rime_bus $end",
        "$var wire 32 a addr $end",
        "$var wire 4 w wstrb $end",
        "$var wire 1 v txn $end",
        "$upscope $end",
        "$enddefinitions $end",
    ]
    for addr, meta in entries:
        ts = meta >> 4
        wstrb = meta & 0xF
        out.append(f"#{ts}")
        out.append(f"b{addr:032b} a")
        out.append(f"b{wstrb:04b} w")
        out.append("1v")
        out.append(f"#{ts + 1}")
        out.append("0v")
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def cmd_trace(args):
    R = _imports()
    fw = _gen_trace_firmware(R)
    print(f"trace: composing rime-i + trace ({len(fw)} instrs)")
    ok, luts = R["build_module"]("trace", fw)
    if not ok:
        R["restore_rime"]()
        raise RuntimeError("trace composition build failed")
    print(f"built: {luts} LUTs; loading and capturing on silicon")
    out = R["flash_and_read"]("trace")
    R["restore_rime"]()
    entries = _parse_trace(out)
    if entries is None:
        raise RuntimeError(f"no trace block in board output: {out[:160]!r}")
    vcd = getattr(args, "vcd", None)
    if vcd:
        vcd = str(Path(vcd).expanduser())
    for line in _render_trace(entries, vcd):
        print(line)
    return {"trace_entries": len(entries), "luts": luts, "vcd": vcd}
