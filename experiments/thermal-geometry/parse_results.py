#!/usr/bin/env python3
"""Parse thermal geometry results — compare constrained vs floating rings."""
import os
import sys

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


def parse_file(path):
    counts = []
    with open(path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if "," in line and line[0].isdigit():
                parts = line.split(",")
                if len(parts) == 2:
                    try:
                        counts.append(int(parts[1], 16))
                    except ValueError:
                        pass
    return counts


def analyze(base_dir):
    print(f"{'Arrangement':25s} {'Placed':>6} {'Mean(P)':>9} {'Mean(F)':>9} "
          f"{'Delta':>7} {'Min(P)':>8} {'Max(P)':>8} {'Range%':>7}")

    for name, n_placed in ARRANGEMENTS:
        path = os.path.join(base_dir, f"results_{name}.txt")
        if not os.path.exists(path):
            print(f"{name:25s}  -- no data --")
            continue

        counts = parse_file(path)
        if not counts:
            print(f"{name:25s}  -- empty --")
            continue

        placed = counts[:n_placed]
        floating = counts[n_placed:] if n_placed < len(counts) else []

        mp = sum(placed) / len(placed)
        mn_p, mx_p = min(placed), max(placed)
        rng = (mx_p - mn_p) / mp * 100 if mp > 0 else 0

        if floating:
            mf = sum(floating) / len(floating)
            delta = (mp - mf) / mf * 100
            print(f"{name:25s} {n_placed:>6} {mp:>9,.0f} {mf:>9,.0f} "
                  f"{delta:>+6.1f}% {mn_p:>8,} {mx_p:>8,} {rng:>6.1f}%")
        else:
            print(f"{name:25s} {n_placed:>6} {mp:>9,.0f} {'N/A':>9} "
                  f"{'N/A':>7} {mn_p:>8,} {mx_p:>8,} {rng:>6.1f}%")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    analyze(base)
