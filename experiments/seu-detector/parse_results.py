#!/usr/bin/env python3
"""Parse SEU detector UART output and summarize results."""

import sys
from pathlib import Path


def parse_seu_log(path: str) -> None:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()

    config = {}
    health_reports = []
    flip_events = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("C,"):
            parts = line[2:].split(",")
            if len(parts) >= 3:
                config = {
                    "groups": int(parts[0], 16),
                    "bits_per_group": int(parts[1], 16),
                    "base_pattern": parts[2],
                }

        elif line.startswith("S,"):
            parts = line[2:].split(",")
            if len(parts) >= 4:
                health_reports.append({
                    "scans": int(parts[0], 16),
                    "flips": int(parts[1], 16),
                    "uptime_s": int(parts[2], 16),
                    "ring_freq": int(parts[3], 16),
                })

        elif line.startswith("F,"):
            parts = line[2:].split(",")
            if len(parts) >= 3:
                flip_events.append({
                    "group": int(parts[0], 16),
                    "xor_mask": int(parts[1], 16),
                    "scan_count": int(parts[2], 16),
                })

    print("=" * 60)
    print("SEU DETECTOR RESULTS")
    print("=" * 60)

    if config:
        total_ffs = config["groups"] * config["bits_per_group"]
        print(f"Configuration: {config['groups']} groups x "
              f"{config['bits_per_group']} bits = {total_ffs} FFs")
        print(f"Base pattern: 0x{config['base_pattern']}")

    if health_reports:
        last = health_reports[-1]
        first = health_reports[0]
        last["uptime_s"] - first["uptime_s"]
        total_scans = last["scans"]
        total_flips = last["flips"]

        print(f"\nMonitoring duration: {last['uptime_s']} seconds")
        print(f"Total scans: {total_scans:,}")
        print(f"Total flips detected: {total_flips}")

        if config and total_scans > 0:
            total_ffs = config["groups"] * config["bits_per_group"]
            bit_checks = total_scans * total_ffs
            print(f"Total bit-checks: {bit_checks:,}")

        freqs = [h["ring_freq"] for h in health_reports]
        if freqs:
            mean_freq = sum(freqs) / len(freqs)
            min_freq = min(freqs)
            max_freq = max(freqs)
            drift_pct = (max_freq - min_freq) / mean_freq * 100 if mean_freq > 0 else 0
            print("\nRing oscillator (temperature proxy):")
            print(f"  Mean frequency: {mean_freq:,.0f} Hz")
            print(f"  Range: {min_freq:,} - {max_freq:,} Hz")
            print(f"  Drift: {drift_pct:.3f}%")

    if flip_events:
        print(f"\n{'='*60}")
        print(f"FLIP EVENTS ({len(flip_events)} detected)")
        print(f"{'='*60}")
        for i, ev in enumerate(flip_events):
            bits_flipped = bin(ev["xor_mask"]).count("1")
            print(f"  Event {i}: group={ev['group']:3d}  "
                  f"xor=0x{ev['xor_mask']:08X} ({bits_flipped} bits)  "
                  f"scan={ev['scan_count']:,}")
    else:
        print("\nNo flip events detected.")
        if health_reports:
            print("This is expected at sea level for this FF count.")
            if config:
                total_ffs = config["groups"] * config["bits_per_group"]
                rate = total_ffs * 1e-14 * 20
                if rate > 0:
                    years = 1.0 / (rate * 8760)
                    print(f"Expected SEU rate: ~1 event per {years:,.0f} years")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <results_file>")
        sys.exit(1)
    parse_seu_log(sys.argv[1])
