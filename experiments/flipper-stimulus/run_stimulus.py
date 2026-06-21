#!/usr/bin/env python3
"""Orchestrate RF sensor grid captures with Flipper Zero and LoRa stimulus.

Workflow:
  1. Capture baseline sweeps (no RF stimulus)
  2. Command Flipper Zero to transmit at 433.92 MHz
  3. Capture stimulus sweeps
  4. Stop Flipper transmission
  5. Capture post-stimulus sweeps
  6. Save all data for differential analysis

Prerequisites:
  - RF sensor bitstream loaded on IcePi Zero (COM9)
  - Flipper Zero on COM4 (230400 baud)
  - LoRa node on COM3 (Meshtastic, optional)

Usage:
  python run_stimulus.py --baseline 5 --stimulus 10 --post 5
  python run_stimulus.py --source flipper --freq 433920000
  python run_stimulus.py --source lora
"""

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def find_serial():
    try:
        import serial
        return serial
    except ImportError:
        print("pyserial required: pip install pyserial")
        sys.exit(1)


def capture_sweeps(port, baud, num_sweeps, output_lines, timeout_per_sweep=2.0):
    """Capture num_sweeps complete sweeps from the RF sensor."""
    serial = find_serial()
    sweeps_captured = 0
    deadline = time.time() + num_sweeps * timeout_per_sweep + 10

    with serial.Serial(port, baud, timeout=0.1) as ser:
        ser.reset_input_buffer()
        buf = ""
        while sweeps_captured < num_sweeps and time.time() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        output_lines.append(line)
                        if line.startswith("T,"):
                            sweeps_captured += 1
                            print(f"  Sweep {sweeps_captured}/{num_sweeps}")
            else:
                time.sleep(0.01)

    return sweeps_captured


def flipper_tx_start(port="COM4", freq=433920000):
    """Command Flipper Zero to start transmitting a carrier."""
    serial = find_serial()
    print(f"Starting Flipper TX at {freq/1e6:.3f} MHz on {port}...")

    with serial.Serial(port, 230400, timeout=2) as ser:
        time.sleep(0.5)
        ser.reset_input_buffer()
        ser.write(b"subghz tx " + str(freq).encode() + b" 1000000\r\n")
        ser.flush()
        time.sleep(0.5)
        response = ser.read(ser.in_waiting or 256)
        print(f"  Flipper response: {response.decode('utf-8', errors='replace').strip()}")

    print("  Flipper TX active")


def flipper_tx_stop(port="COM4"):
    """Stop Flipper Zero transmission."""
    serial = find_serial()
    print(f"Stopping Flipper TX on {port}...")

    with serial.Serial(port, 230400, timeout=2) as ser:
        time.sleep(0.3)
        ser.reset_input_buffer()
        ser.write(b"\x03")
        ser.flush()
        time.sleep(0.5)
        response = ser.read(ser.in_waiting or 256)
        print(f"  Flipper response: {response.decode('utf-8', errors='replace').strip()}")

    print("  Flipper TX stopped")


def lora_tx_burst(port="COM3"):
    """Trigger a LoRa transmission burst via Meshtastic CLI."""
    print(f"Triggering LoRa TX burst via Meshtastic on {port}...")
    try:
        import subprocess
        result = subprocess.run(
            ["meshtastic", "--port", port, "--sendtext", "RF_SENSOR_PROBE"],
            capture_output=True, text=True, timeout=10
        )
        print(f"  Meshtastic output: {result.stdout.strip()}")
        if result.returncode != 0:
            print(f"  Warning: {result.stderr.strip()}")
    except FileNotFoundError:
        print("  meshtastic CLI not found. Skipping LoRa burst.")
    except Exception as e:
        print(f"  LoRa TX failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="RF sensor stimulus experiment")
    parser.add_argument("--fpga-port", default="COM9", help="FPGA serial port")
    parser.add_argument("--fpga-baud", type=int, default=115200)
    parser.add_argument("--flipper-port", default="COM4", help="Flipper Zero port")
    parser.add_argument("--lora-port", default="COM3", help="LoRa/Meshtastic port")
    parser.add_argument("--source", choices=["flipper", "lora", "both"],
                        default="flipper", help="RF stimulus source")
    parser.add_argument("--freq", type=int, default=433920000,
                        help="Flipper TX frequency in Hz")
    parser.add_argument("--baseline", type=int, default=5,
                        help="Number of baseline sweeps")
    parser.add_argument("--stimulus", type=int, default=10,
                        help="Number of stimulus sweeps")
    parser.add_argument("--post", type=int, default=5,
                        help="Number of post-stimulus sweeps")
    parser.add_argument("--output", default=None,
                        help="Output file (default: results_<source>.txt)")
    args = parser.parse_args()

    if args.output is None:
        args.output = f"results_{args.source}.txt"

    all_lines = []
    all_lines.append("# RF Stimulus Experiment")
    all_lines.append(f"# Source: {args.source}")
    all_lines.append(f"# Frequency: {args.freq} Hz")
    all_lines.append(f"# Baseline sweeps: {args.baseline}")
    all_lines.append(f"# Stimulus sweeps: {args.stimulus}")
    all_lines.append(f"# Post-stimulus sweeps: {args.post}")
    all_lines.append(f"# Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    all_lines.append("")

    print(f"\n=== Phase 1: Baseline ({args.baseline} sweeps) ===")
    all_lines.append("# PHASE: BASELINE")
    baseline_lines = []
    n = capture_sweeps(args.fpga_port, args.fpga_baud, args.baseline, baseline_lines)
    all_lines.extend(baseline_lines)
    print(f"  Captured {n} baseline sweeps")

    print(f"\n=== Phase 2: Stimulus ({args.stimulus} sweeps) ===")
    all_lines.append("")
    all_lines.append("# PHASE: STIMULUS")

    if args.source in ("flipper", "both"):
        flipper_tx_start(args.flipper_port, args.freq)
        time.sleep(1)

    if args.source in ("lora", "both"):
        lora_tx_burst(args.lora_port)
        time.sleep(1)

    stimulus_lines = []
    n = capture_sweeps(args.fpga_port, args.fpga_baud, args.stimulus, stimulus_lines)
    all_lines.extend(stimulus_lines)
    print(f"  Captured {n} stimulus sweeps")

    if args.source in ("flipper", "both"):
        flipper_tx_stop(args.flipper_port)

    print(f"\n=== Phase 3: Post-stimulus ({args.post} sweeps) ===")
    all_lines.append("")
    all_lines.append("# PHASE: POST-STIMULUS")
    post_lines = []
    n = capture_sweeps(args.fpga_port, args.fpga_baud, args.post, post_lines)
    all_lines.extend(post_lines)
    print(f"  Captured {n} post-stimulus sweeps")

    output_path = Path(__file__).parent / args.output
    output_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    print(f"\nResults saved to {output_path}")
    print(f"Run parse_differential.py {args.output} to analyze.")


if __name__ == "__main__":
    main()
