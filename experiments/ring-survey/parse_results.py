#!/usr/bin/env python3
"""Parse ring survey results and compute process variation statistics."""
import sys
from pathlib import Path


def parse(path, label=""):
    text = Path(path).read_text(errors="replace")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    counts = []
    large = None
    for line in lines:
        if line.startswith("R,"):
            parts = line.split(",")
            if len(parts) == 3:
                idx = int(parts[1], 16)
                cnt = int(parts[2], 16)
                counts.append((idx, cnt))
        elif line.startswith("L,"):
            large = int(line.split(",")[1], 16)

    if not counts:
        print("No ring data found.")
        return

    vals = [c for _, c in counts]
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = variance ** 0.5
    cv = std / mean if mean > 0 else 0

    title = label or lines[0] if lines else "Ring Survey"
    print(f"=== {title} ===")
    print(f"Small rings: {len(counts)}")
    print(f"  Mean:   {mean:>10,.0f} edges/10ms")
    print(f"  Std:    {std:>10,.0f}")
    print(f"  CV:     {cv:.4f} ({cv*100:.2f}%)")
    print(f"  Min:    {min(vals):>10,} (ring {[i for i,v in counts if v==min(vals)][0]})")
    print(f"  Max:    {max(vals):>10,} (ring {[i for i,v in counts if v==max(vals)][0]})")
    print(f"  Range:  {max(vals)-min(vals):>10,} ({(max(vals)-min(vals))/mean*100:.1f}%)")
    print(f"  Median: {sorted(vals)[len(vals)//2]:>10,}")

    lo, hi = min(vals), max(vals)
    if hi > lo:
        bin_width = (hi - lo) / 10
        bins = [0] * 10
        for v in vals:
            b = min(int((v - lo) / bin_width), 9)
            bins[b] += 1
        print("\n  Distribution (10 bins):")
        for i, b in enumerate(bins):
            bar = "#" * (b * 40 // max(bins)) if max(bins) > 0 else ""
            lo_edge = lo + i * bin_width
            print(f"    {lo_edge:>8,.0f}: {b:>4} {bar}")

    if large is not None:
        print(f"\nLarge ring: {large:,} edges/10ms")
        print("  (aliased edge count — true frequency is a harmonic)")

    return counts, large


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_results.py <results_file> [label]")
        sys.exit(1)
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    parse(sys.argv[1], label)
