#!/usr/bin/env python3
"""Parse RF sensor grid UART output and analyze frequency maps."""

import sys
from pathlib import Path
from collections import defaultdict


def parse_rf_log(path: str) -> None:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()

    config = {}
    sweeps: dict[int, dict[int, int]] = defaultdict(dict)
    sweep_freqs: dict[int, int] = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("G,"):
            parts = line[2:].split(",")
            if len(parts) >= 4:
                config = {
                    "grid_w": int(parts[0], 16),
                    "grid_h": int(parts[1], 16),
                    "meas_ms": int(parts[2], 16),
                    "total_rings": int(parts[3], 16),
                }

        elif line.startswith("R,"):
            parts = line[2:].split(",")
            if len(parts) >= 3:
                sweep = int(parts[0], 16)
                idx = int(parts[1], 16)
                count = int(parts[2], 16)
                sweeps[sweep][idx] = count

        elif line.startswith("T,"):
            parts = line[2:].split(",")
            if len(parts) >= 2:
                sweep = int(parts[0], 16)
                freq = int(parts[1], 16)
                sweep_freqs[sweep] = freq

    print("=" * 60)
    print("RF SENSOR GRID RESULTS")
    print("=" * 60)

    if config:
        print(f"Grid: {config['grid_w']}x{config['grid_h']} = "
              f"{config['total_rings']} rings")
        print(f"Measurement window: {config['meas_ms']} ms")

    num_sweeps = len(sweeps)
    print(f"Sweeps captured: {num_sweeps}")

    if not sweeps:
        print("No data.")
        return

    print(f"\n{'Sweep':>6} {'Mean':>8} {'StdDev':>8} {'Min':>8} {'Max':>8} "
          f"{'Spread%':>8} {'RingFreq':>10}")
    print("-" * 70)

    all_means = []
    for sweep_num in sorted(sweeps.keys()):
        data = sweeps[sweep_num]
        if not data:
            continue
        counts = list(data.values())
        mean = sum(counts) / len(counts)
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        std = variance ** 0.5
        mn, mx = min(counts), max(counts)
        spread = (mx - mn) / mean * 100 if mean > 0 else 0
        freq = sweep_freqs.get(sweep_num, 0)
        all_means.append(mean)
        print(f"{sweep_num:>6} {mean:>8.0f} {std:>8.1f} {mn:>8} {mx:>8} "
              f"{spread:>7.2f}% {freq:>10}")

    if num_sweeps >= 2:
        first = sweeps[min(sweeps.keys())]
        last = sweeps[max(sweeps.keys())]
        common_indices = set(first.keys()) & set(last.keys())

        if common_indices:
            diffs = []
            for idx in sorted(common_indices):
                diff = last[idx] - first[idx]
                diffs.append((idx, diff))

            abs_diffs = [abs(d) for _, d in diffs]
            mean_drift = sum(d for _, d in diffs) / len(diffs)
            max_drift_idx, max_drift = max(diffs, key=lambda x: abs(x[1]))

            print("\nCross-sweep drift (first vs last):")
            print(f"  Mean drift: {mean_drift:+.1f} counts")
            print(f"  Max drift: {max_drift:+d} at ring {max_drift_idx}")
            print(f"  Mean |drift|: {sum(abs_diffs)/len(abs_diffs):.1f} counts")

    if config and num_sweeps > 0:
        last_sweep = sweeps[max(sweeps.keys())]
        w = config["grid_w"]
        h = config["grid_h"]
        print(f"\nSpatial frequency map (last sweep, {w}x{h}):")
        print("  (row major, values in edge counts per {config['meas_ms']}ms)")

        for row in range(h):
            vals = []
            for col in range(w):
                idx = row * w + col
                count = last_sweep.get(idx, 0)
                vals.append(f"{count:5d}")
            print(f"  Row {row:2d}: {' '.join(vals)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <results_file>")
        sys.exit(1)
    parse_rf_log(sys.argv[1])
