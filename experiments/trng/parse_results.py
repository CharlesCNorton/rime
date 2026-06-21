#!/usr/bin/env python3
"""Parse TRNG experiment UART output and verify uniform distribution."""
import sys
from pathlib import Path

def parse(path):
    data = Path(path).read_bytes()
    text = data.decode("ascii", errors="replace")
    lines = [ln.strip() for ln in text.split("\n") if "," in ln and ln[0].isdigit()]
    bins = {}
    for line in lines:
        parts = line.split(",")
        if len(parts) == 3:
            ch, bn, cnt = int(parts[0], 16), int(parts[1], 16), int(parts[2], 16)
            bins[(ch, bn)] = cnt
    if not bins:
        print("No histogram data found.")
        return
    counts = list(bins.values())
    total = sum(counts)
    mean = total / len(counts)
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    chi2 = sum((c - mean) ** 2 / mean for c in counts) if mean > 0 else 0
    print(f"Channels: {max(ch for ch, _ in bins) + 1}")
    print(f"Bins per channel: {max(bn for _, bn in bins) + 1}")
    print(f"Total entries: {len(bins)}")
    print(f"Total samples: {total}")
    print(f"Mean per bin: {mean:.1f}")
    print(f"Std dev: {variance**0.5:.1f}")
    print(f"CV (std/mean): {variance**0.5/mean:.4f}" if mean > 0 else "")
    print(f"Chi-squared: {chi2:.1f} (expect ~{len(counts)-1} for uniform)")
    print(f"Uniformity: {'PASS' if chi2 < 2 * len(counts) else 'FAIL'}")

if __name__ == "__main__":
    parse(sys.argv[1] if len(sys.argv) > 1 else "results_raw.bin")
