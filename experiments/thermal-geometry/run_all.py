#!/usr/bin/env python3
"""Build, load, and capture all 10 thermal geometry arrangements."""

import os
import subprocess
import sys
import time

import serial

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(BASE, "..", "..")
LPF = os.path.join(REPO, "firmware", "icepi-zero.lpf")
TOP_SV = os.path.join(BASE, "top.sv")
UART_RX = os.path.join(REPO, "firmware", "core", "uart_rx.sv")
UART_TX = os.path.join(REPO, "firmware", "core", "uart_tx.sv")
ADMIN = os.path.join(REPO, "icepi_admin.py")
OFL = r"D:\oss-cad-suite\bin\openFPGALoader.exe"
ENV_BAT = r"D:\oss-cad-suite\environment.bat"

ARRANGEMENTS = [
    ("01_full_saturation", 759),
    ("02_checkerboard", 380),
    ("03_isolation_radial", 13),
    ("04_stripe_gradient", 374),
    ("05_single_hot_row", 75),
    ("06_corner_source", 35),
    ("07_density_sweep", 25),
    ("08_opposing_walls", 31),
    ("09_concentric_rect", 70),
    ("10_spiral", 409),
]


def run_cmd(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ps1(action, timeout=120):
    subprocess.run(
        [sys.executable, ADMIN, action],
        capture_output=True, timeout=timeout,
    )


def synthesize_once():
    """Synthesize with nosis once — the HDL is the same for all arrangements."""
    json_out = os.path.join(BASE, "bitstream.json")
    if os.path.exists(json_out):
        return True
    print("  Synthesizing (one-time)...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "nosis", TOP_SV, UART_RX, UART_TX,
         "--top", "top", "-o", json_out],
        capture_output=True, text=True, timeout=300, cwd=BASE,
    )
    return os.path.exists(json_out)


def build(name, num_rings):
    """Place + route with arrangement-specific pre-place script."""
    json_out = os.path.join(BASE, "bitstream.json")
    config_out = os.path.join(BASE, "bitstream.config")
    bit_out = os.path.join(BASE, "bitstream.bit")
    place_script = os.path.join(BASE, f"place_{name}.py")

    for f in [config_out, bit_out]:
        if os.path.exists(f):
            os.remove(f)

    if not os.path.exists(json_out):
        print("  No synthesis output — run synthesize_once() first")
        return False

    npr_ps = (
        f"cmd /c 'call {ENV_BAT} && nextpnr-ecp5 --25k --package CABGA256 "
        f"--lpf {LPF} --json {json_out} --textcfg {config_out} "
        f"--pre-place {place_script} --ignore-loops --timing-allow-fail'"
    )
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", npr_ps],
        capture_output=True, text=True, timeout=600, cwd=BASE,
    )
    if not os.path.exists(config_out):
        print(f"  P&R FAILED for {name}")
        return False

    pack_ps = f"cmd /c 'call {ENV_BAT} && ecppack --compress {config_out} {bit_out}'"
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", pack_ps],
        capture_output=True, timeout=60, cwd=BASE,
    )

    return os.path.exists(bit_out)


def load_and_capture(name, num_rings):
    """JTAG load, switch to UART, capture data."""
    bit_path = os.path.join(BASE, "bitstream.bit")
    result_path = os.path.join(BASE, f"results_{name}.txt")

    ps1("jtag")
    time.sleep(1)

    load_ps = f"cmd /c 'call {ENV_BAT} && {OFL} -b icepi-zero --freq 3000000 {bit_path}'"
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", load_ps],
        capture_output=True, timeout=60,
    )
    if b"Done" not in r.stdout and b"Done" not in r.stderr:
        print(f"  LOAD FAILED for {name}")
        ps1("uart")
        return False

    ps1("uart")
    time.sleep(2)

    sweep_time = max(20 + num_rings * 0.01 + 5, 30)
    timeout_s = int(sweep_time + 30)

    s = serial.Serial("COM9", 115200, timeout=timeout_s)
    time.sleep(1)
    s.reset_input_buffer()
    data = b""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        chunk = s.read(4096)
        if chunk:
            data += chunk
            if b"DONE" in data:
                break
    s.close()

    with open(result_path, "wb") as f:
        f.write(data)

    text = data.decode("ascii", errors="replace")
    lines = [ln.strip() for ln in text.split("\n") if "," in ln and ln[0].isdigit()]
    counts = []
    for line in lines:
        parts = line.split(",")
        if len(parts) == 2:
            try:
                counts.append(int(parts[1], 16))
            except ValueError:
                pass

    return counts


def main():
    if not synthesize_once():
        print("SYNTHESIS FAILED — cannot continue")
        return

    results = {}
    for name, num_rings in ARRANGEMENTS:
        print(f"\n{'='*60}")
        print(f"  {name}  ({num_rings} rings)")
        print(f"{'='*60}")

        print("  Building...", flush=True)
        if not build(name, num_rings):
            results[name] = "BUILD FAILED"
            continue

        print("  Loading + capturing...", flush=True)
        counts = load_and_capture(name, num_rings)
        if not counts:
            results[name] = "CAPTURE FAILED"
            continue

        mean = sum(counts) / len(counts) if counts else 0
        mn = min(counts) if counts else 0
        mx = max(counts) if counts else 0
        rng = (mx - mn) / mean * 100 if mean > 0 else 0

        print(f"  Rings: {len(counts)}")
        print(f"  Mean:  {mean:,.0f}")
        print(f"  Range: {mn:,} - {mx:,} ({rng:.1f}%)")
        results[name] = {
            "rings": len(counts),
            "mean": mean,
            "min": mn,
            "max": mx,
            "range_pct": rng,
        }

    print("\nRestoring board...")
    ps1("reload")

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for name, _ in ARRANGEMENTS:
        r = results.get(name, "NOT RUN")
        if isinstance(r, dict):
            print(f"  {name:25s}  {r['rings']:>5} rings  "
                  f"mean={r['mean']:>8,.0f}  range={r['range_pct']:.1f}%")
        else:
            print(f"  {name:25s}  {r}")


if __name__ == "__main__":
    main()
