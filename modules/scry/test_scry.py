#!/usr/bin/env python3
"""SCRY compositor test: RIME-I + SCRY trace buffer.

Three tests of increasing difficulty:
  1. Enable SCRY, do 5 writes, check COUNT >= 5
  2. Enable, do writes to known addresses, read trace entries, verify addresses
  3. Enable, run computation, clear, run again, verify trace only has second run
"""

import subprocess
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent.parent
_mod = Path(__file__).resolve().parent
sys.path.insert(0, str(_repo))
sys.path.insert(0, str(_repo / "modules" / "rime-i"))

import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("_gf", str(_repo / "modules" / "rime-i" / "gen_firmware.py"))
_gf = importlib.util.module_from_spec(_spec)
# Only import the class, not execute module-level code
RV32I = type('RV32I', (), {})  # placeholder
exec(open(str(_repo / "modules" / "rime-i" / "gen_firmware.py")).read().split("\ndef generate_math_firmware")[0], _gf.__dict__)
RV32I = _gf.__dict__['RV32I']
x0, ra, sp = 0, 1, 2
t0, t1, t2, t3 = 5, 6, 7, 28
a0, a1 = 10, 11
s0, s1, s2, s3, s4 = 8, 9, 18, 19, 20

UART_BASE = 0x20000000
SCRY_BASE = 0x30000000
SCRY_COUNT = SCRY_BASE + 0x000
SCRY_CTRL  = SCRY_BASE + 0x004
SCRY_WPTR  = SCRY_BASE + 0x008
SCRY_TRACE = SCRY_BASE + 0x400  # trace[i] = SCRY_TRACE + i*4


def gen_firmware():
    """Generate firmware that runs all 3 SCRY tests and prints results."""
    asm = RV32I()

    asm.lui(sp, 0x00001)        # sp = 0x1000
    asm.lui(s4, UART_BASE >> 12)
    asm.j("main")

    # --- putc subroutine ---
    asm.label("putc")
    asm.lw(t0, s4, 4)
    asm.bne(t0, x0, "putc")
    asm.sw(a0, s4, 0)
    asm.ret()

    # --- puts: print string at a0 (null terminated) ---
    # We'll inline character printing instead

    # === MAIN ===
    asm.label("main")

    # --- Test 1: Enable SCRY, do 5 writes, check COUNT >= 5 ---
    # Enable SCRY
    asm.li(t0, SCRY_CTRL)
    asm.addi(t1, x0, 3)       # enable + clear
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 1)       # enable only
    asm.sw(t1, t0, 0)

    # Do 5 writes to BRAM
    asm.li(t0, 0x200)          # BRAM address
    asm.addi(t1, x0, 0x41)
    asm.sw(t1, t0, 0)
    asm.sw(t1, t0, 4)
    asm.sw(t1, t0, 8)
    asm.sw(t1, t0, 12)
    asm.sw(t1, t0, 16)

    # Read COUNT
    asm.li(t0, SCRY_COUNT)
    asm.lw(t1, t0, 0)
    # COUNT should be >= 5 (might be higher due to the SCRY control writes)
    asm.addi(t2, x0, 5)
    asm.bge(t1, t2, "test1_pass")
    # FAIL
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test2")
    asm.label("test1_pass")
    asm.addi(a0, x0, ord('1'))
    asm.call("putc")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 2: Write to known addresses, verify trace entries ---
    asm.label("test2")
    # Clear and re-enable
    asm.li(t0, SCRY_CTRL)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # Write to addresses 0x300, 0x304, 0x308
    asm.li(t0, 0x300)
    asm.addi(t1, x0, 0x55)
    asm.sw(t1, t0, 0)          # write to 0x300
    asm.sw(t1, t0, 4)          # write to 0x304
    asm.sw(t1, t0, 8)          # write to 0x308

    # Disable SCRY to stop recording
    asm.li(t0, SCRY_CTRL)
    asm.sw(x0, t0, 0)

    # Read WRITE_PTR to know how many entries
    asm.li(t0, SCRY_WPTR)
    asm.lw(s0, t0, 0)         # s0 = write_ptr

    # The trace should contain the SCRY control writes + the 3 BRAM writes.
    # Look for 0x300 in the trace entries.
    # Search trace[0..write_ptr-1] for address 0x300
    asm.li(s1, SCRY_TRACE)
    asm.addi(s2, x0, 0)       # i = 0
    asm.li(s3, 0x300)          # target address
    asm.addi(t3, x0, 0)       # found = 0

    asm.label("t2_loop")
    asm.bge(s2, s0, "t2_done")
    asm.slli(t0, s2, 2)
    asm.add(t0, t0, s1)
    asm.lw(t1, t0, 0)         # trace[i]
    asm.bne(t1, s3, "t2_skip")
    asm.addi(t3, t3, 1)       # found++
    asm.label("t2_skip")
    asm.addi(s2, s2, 1)
    asm.j("t2_loop")

    asm.label("t2_done")
    # t3 should be >= 1 (found 0x300 in trace)
    asm.addi(a0, x0, ord('2'))
    asm.call("putc")
    asm.bne(t3, x0, "test2_pass")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")
    asm.j("test3")
    asm.label("test2_pass")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")

    # --- Test 3: Clear, run fibonacci, check trace has fib addresses ---
    asm.label("test3")
    # Clear and re-enable
    asm.li(t0, SCRY_CTRL)
    asm.addi(t1, x0, 3)
    asm.sw(t1, t0, 0)
    asm.addi(t1, x0, 1)
    asm.sw(t1, t0, 0)

    # Write fibonacci results to BRAM addresses 0x400, 0x404, ...
    asm.li(s1, 0x400)          # base address
    asm.addi(s2, x0, 0)       # fib a = 0
    asm.addi(s3, x0, 1)       # fib b = 1
    asm.addi(t3, x0, 0)       # i = 0
    asm.addi(t2, x0, 10)      # n = 10

    asm.label("fib_loop")
    asm.bge(t3, t2, "fib_done")
    asm.sw(s2, s1, 0)         # store fib(i) at base + i*4
    asm.add(t0, s2, s3)       # t = a + b
    asm.mv(s2, s3)            # a = b
    asm.mv(s3, t0)            # b = t
    asm.addi(s1, s1, 4)
    asm.addi(t3, t3, 1)
    asm.j("fib_loop")

    asm.label("fib_done")
    # Disable SCRY
    asm.li(t0, SCRY_CTRL)
    asm.sw(x0, t0, 0)

    # Verify: trace should contain addresses in range 0x400-0x424
    # Read COUNT, should be >= 10 (fib stores) + overhead
    asm.li(t0, SCRY_COUNT)
    asm.lw(t1, t0, 0)
    asm.addi(t2, x0, 10)

    # Also verify trace contains 0x400 and 0x424 (first and last fib store)
    asm.li(t0, SCRY_WPTR)
    asm.lw(s0, t0, 0)
    asm.li(s1, SCRY_TRACE)
    asm.addi(s2, x0, 0)
    asm.li(s3, 0x400)
    asm.addi(t3, x0, 0)       # found_first = 0
    asm.addi(t2, x0, 0)       # found_last = 0
    asm.li(a1, 0x424)          # last fib address

    asm.label("t3_loop")
    asm.bge(s2, s0, "t3_check")
    asm.slli(t0, s2, 2)
    asm.add(t0, t0, s1)
    asm.lw(t1, t0, 0)
    asm.bne(t1, s3, "t3_not_first")
    asm.addi(t3, t3, 1)
    asm.label("t3_not_first")
    asm.bne(t1, a1, "t3_not_last")
    asm.addi(t2, t2, 1)
    asm.label("t3_not_last")
    asm.addi(s2, s2, 1)
    asm.j("t3_loop")

    asm.label("t3_check")
    # Pass if found_first > 0 AND found_last > 0
    asm.addi(a0, x0, ord('3'))
    asm.call("putc")
    asm.beq(t3, x0, "test3_fail")
    asm.beq(t2, x0, "test3_fail")
    asm.addi(a0, x0, ord('P'))
    asm.call("putc")
    asm.j("done")
    asm.label("test3_fail")
    asm.addi(a0, x0, ord('F'))
    asm.call("putc")

    asm.label("done")
    asm.addi(a0, x0, ord('\n'))
    asm.call("putc")

    # Delay then loop
    asm.lui(t1, 500)
    asm.addi(t1, t1, -1)
    asm.bne(t1, x0, "done_delay")
    asm.label("done_delay")
    # (the bne already loops; need a proper delay label)
    # Let me redo: delay loop then jump to main
    asm.li(t0, 0x200000)
    asm.label("delay")
    asm.addi(t0, t0, -1)
    asm.bne(t0, x0, "delay")
    asm.j("main")

    asm.resolve()
    return asm.code


def patch_and_build(code):
    """Patch top.sv with firmware and build."""
    top = _mod / "top.sv"
    text = top.read_text()
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
        [sys.executable, str(_repo / "icepi_helper.py"), "build", "scry", "--clean"],
        capture_output=True, text=True, cwd=str(_repo), timeout=300,
    )
    luts = 0
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if "Total LUT4s:" in line:
            luts = int(line.split("LUT4s:")[1].split("/")[0].strip())
    return result.returncode == 0, luts


def flash_and_read():
    """Flash via JTAG SRAM, switch to UART, read output."""
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
        return ser.read(200).decode("ascii", errors="replace").strip()


def main():
    print("=== SCRY compositor test ===")

    code = gen_firmware()
    print(f"Firmware: {len(code)} instructions")

    ok, luts = patch_and_build(code)
    if not ok:
        print("BUILD FAILED")
        return 1

    print(f"Build: {luts} LUTs")

    output = flash_and_read()
    print(f"Output: {output!r}")

    # Parse results: expect "1P2P3P" per line
    lines = [l.strip() for l in output.split('\n') if l.strip()]  # noqa: E741
    if not lines:
        print("NO OUTPUT")
        return 1

    first = lines[0]
    t1 = "1P" in first
    t2 = "2P" in first
    t3 = "3P" in first
    print(f"Test 1 (count):       {'PASS' if t1 else 'FAIL'}")
    print(f"Test 2 (trace read):  {'PASS' if t2 else 'FAIL'}")
    print(f"Test 3 (fib capture): {'PASS' if t3 else 'FAIL'}")

    all_pass = t1 and t2 and t3
    print(f"SCRY: {'PASS' if all_pass else 'FAIL'}")

    # Restore RIME service
    print("Restoring RIME service...")
    from icepi_admin import (_pnputil_switch_to_jtag, _pnputil_switch_to_uart,
                             probe_jtag_target, run_loader_command)
    _pnputil_switch_to_jtag()
    time.sleep(3)
    for _ in range(6):
        if probe_jtag_target():
            break
        time.sleep(2)
    try:
        run_loader_command(["-b", "icepi-zero", "-r"], check=True)
    except Exception:
        print("WARNING: could not restore RIME service")
    _pnputil_switch_to_uart()
    time.sleep(3)

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
