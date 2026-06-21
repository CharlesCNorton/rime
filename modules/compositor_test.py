#!/usr/bin/env python3
"""Shared test runner for compositor module tests.

Usage from a module test script:
    from compositor_test import run_module_test, RV32I, REGS
    asm = RV32I()
    # ... generate firmware ...
    run_module_test("modname", asm.code, expected="1P2P3P")
"""

import subprocess
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

# Import RV32I assembler (only the class, not the module-level code)
_gf_path = _repo / "modules" / "rime-i" / "gen_firmware.py"
_gf_src = _gf_path.read_text()
_gf_ns = {}
exec(_gf_src.split("\ndef generate_math_firmware")[0], _gf_ns)
RV32I = _gf_ns['RV32I']

# Register aliases
x0, ra, sp = 0, 1, 2
t0, t1, t2, t3, t4, t5 = 5, 6, 7, 28, 29, 30
a0, a1, a2 = 10, 11, 12
s0, s1, s2, s3, s4 = 8, 9, 18, 19, 20

# Standard addresses
UART_BASE = 0x20000000
MOD_BASE  = 0x30000000


def build_module(mod_name: str, firmware: list[int]) -> tuple[bool, int]:
    """Generate top.sv, build, return (success, luts)."""
    from compositor_template import generate_top_sv

    mod_dir = _repo / "modules" / mod_name
    generate_top_sv(mod_name, firmware, mod_dir / "top.sv")

    result = subprocess.run(
        [sys.executable, str(_repo / "icepi_helper.py"),
         "build", mod_name, "--clean"],
        capture_output=True, text=True, cwd=str(_repo), timeout=300,
    )
    luts = 0
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if "Total LUT4s:" in line:
            luts = int(line.split("LUT4s:")[1].split("/")[0].strip())
    return result.returncode == 0, luts


def flash_and_read(mod_name: str) -> str:
    """Flash via JTAG SRAM, switch to UART, read output."""
    from icepi_admin import (_pnputil_switch_to_jtag, _pnputil_switch_to_uart,
                             probe_jtag_target, run_loader_command)

    mod_dir = _repo / "modules" / mod_name
    _pnputil_switch_to_jtag()
    time.sleep(3)
    for _ in range(6):
        if probe_jtag_target():
            break
        time.sleep(2)
    run_loader_command(["-b", "icepi-zero", str(mod_dir / "bitstream.bit")], check=True)
    _pnputil_switch_to_uart()
    time.sleep(5)

    import serial.tools.list_ports
    import serial
    port = next((p.device for p in serial.tools.list_ports.comports()
                 if "0403" in (p.hwid or "")), None)
    if not port:
        return ""
    with serial.Serial(port, 115200, timeout=15) as ser:
        return ser.read(8000).decode("ascii", errors="replace").strip()


def restore_rime():
    """Restore RIME service via JTAG reload."""
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
        print("  WARNING: could not restore RIME service")
    _pnputil_switch_to_uart()
    time.sleep(3)


def run_module_test(mod_name: str, firmware: list[int], expected: str = "1P2P3P") -> bool:
    """Build, flash, verify a compositor module test. Returns True if all pass."""
    print(f"=== {mod_name.upper()} compositor test ===")
    print(f"Firmware: {len(firmware)} instructions")

    ok, luts = build_module(mod_name, firmware)
    if not ok:
        print("BUILD FAILED")
        restore_rime()
        return False
    print(f"Build: {luts} LUTs")

    output = flash_and_read(mod_name)
    print(f"Output: {output[:80]!r}")

    lines = [l.strip() for l in output.split('\n') if l.strip()]  # noqa: E741
    if not lines:
        print("NO OUTPUT")
        restore_rime()
        return False

    first = lines[0]
    results = []
    for i in range(1, 4):
        label = f"{i}P"
        passed = label in first
        results.append(passed)
        test_names = {1: "basic", 2: "medium", 3: "hard"}
        print(f"  Test {i} ({test_names[i]}): {'PASS' if passed else 'FAIL'}")

    all_pass = all(results)
    print(f"{mod_name.upper()}: {'PASS' if all_pass else 'FAIL'}")

    restore_rime()
    return all_pass
