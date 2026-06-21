#!/usr/bin/env python3
"""Analyze entropy source output — uniformity, bias, correlation, runs."""
import sys
from pathlib import Path


def analyze(path):
    data = Path(path).read_bytes()
    if not data:
        print("Empty file.")
        return

    n = len(data)
    print(f"Entropy bytes: {n:,}")

    hist = [0] * 256
    for b in data:
        hist[b] += 1
    mean = n / 256.0
    chi2 = sum((h - mean) ** 2 / mean for h in hist)
    print("\nByte uniformity:")
    print(f"  Chi-squared: {chi2:.0f} (expect ~255, reject >310)")
    print(f"  Min bin: {min(hist)} ({min(hist)/mean*100:.1f}%)")
    print(f"  Max bin: {max(hist)} ({max(hist)/mean*100:.1f}%)")
    print(f"  {'PASS' if chi2 < 310 else 'FAIL'}")

    ones = sum(bin(b).count("1") for b in data)
    total = n * 8
    print("\nBit bias:")
    print(f"  Ones: {ones:,} / {total:,} ({ones/total*100:.4f}%)")
    bias = abs(ones / total - 0.5)
    print(f"  Deviation from 50%: {bias*100:.4f}%")
    print(f"  {'PASS' if bias < 0.01 else 'FAIL'}")

    same = sum(1 for i in range(n - 1) if data[i] == data[i + 1])
    print("\nSerial correlation (byte lag-1):")
    print(f"  Identical pairs: {same} / {n-1}")
    print(f"  Rate: {same/(n-1)*100:.4f}% (expect {100/256:.4f}%)")
    print(f"  {'PASS' if abs(same/(n-1) - 1/256) < 0.001 else 'FAIL'}")

    sample = min(n, 10000)
    bits = "".join(format(b, "08b") for b in data[:sample])
    runs = 1
    for i in range(1, len(bits)):
        if bits[i] != bits[i - 1]:
            runs += 1
    n0 = bits.count("0")
    n1 = bits.count("1")
    expected_runs = 1 + 2 * n0 * n1 / (n0 + n1) if (n0 + n1) > 0 else 0
    ratio = runs / expected_runs if expected_runs > 0 else 0
    print(f"\nRuns test ({len(bits):,} bits):")
    print(f"  Runs: {runs:,}")
    print(f"  Expected: {expected_runs:,.0f}")
    print(f"  Ratio: {ratio:.4f}")
    print(f"  {'PASS' if 0.98 < ratio < 1.02 else 'FAIL'}")


if __name__ == "__main__":
    analyze(sys.argv[1] if len(sys.argv) > 1 else "results_entropy.bin")
