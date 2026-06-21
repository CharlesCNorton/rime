#!/usr/bin/env python3
"""EMBER visualization: renders silicon capture data from RIME-I + EMBER composition.

Reads tagged hex CSV lines from the composition firmware output and renders:
  1. Topology rotation timeline (which of 4 XOR topologies is active over time)
  2. Entropy throughput curve (conditioned bytes per frame interval)
  3. Ring frequency stability
  4. Live topology switch event markers
  5. Byte distribution histogram of captured entropy

Data source: modules/compositions/ember_direct_capture.txt
All primitives derived from actual IcePi Zero UART output. No synthetic data.

Usage:
    python scripts/ember_viz.py                                   # from captured file
    python scripts/ember_viz.py --live COM837                     # live from board
    python scripts/ember_viz.py modules/compositions/ember_direct_capture.txt
"""

import sys
from pathlib import Path

DEFAULT_CAPTURE = Path(__file__).resolve().parent.parent / "modules" / "compositions" / "ember_direct_capture.txt"

TOPO_NAMES = ["concentric", "radial", "hot_row", "opposing"]
TOPO_COLORS = ["\033[96m", "\033[93m", "\033[92m", "\033[91m"]  # cyan, yellow, green, red
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
BAR_FULL = "\u2588"
BAR_7_8 = "\u2589"
BAR_HALF = "\u2584"
BAR_1_4 = "\u2582"
BAR_EMPTY = " "


def parse_frame(line):
    """Parse one CSV line: ST:HEX,RF:HEX,SK:HEX,TP:HEX,EC:HEX,EN:HEX"""
    fields = {}
    for part in line.strip().split(","):
        if ":" in part:
            tag, val = part.split(":", 1)
            try:
                fields[tag.strip()] = int(val.strip(), 16)
            except ValueError:
                pass
    return fields


def render_topology_bar(active_topo, width=40):
    """Render a colored bar showing the active topology."""
    name = TOPO_NAMES[active_topo] if active_topo < 4 else "?"
    color = TOPO_COLORS[active_topo] if active_topo < 4 else ""
    bar = color + BAR_FULL * width + RESET
    return f"{bar} {color}{name}{RESET}"


def render_entropy_bar(rate, max_rate, width=50):
    """Render a throughput bar scaled to max_rate."""
    if max_rate <= 0:
        return " " * width
    filled = int(rate / max_rate * width)
    filled = min(filled, width)
    return DIM + BAR_FULL * filled + BAR_EMPTY * (width - filled) + RESET


def render_histogram(byte_counts, width=64, height=8):
    """Render a 256-bin byte histogram as ASCII art."""
    if not byte_counts:
        return ["  (no entropy data)"]
    # Bin 256 values into `width` columns
    bin_size = 256 / width
    bins = [0] * width
    for val, count in byte_counts.items():
        b = min(int(val / bin_size), width - 1)
        bins[b] += count
    max_bin = max(bins) if bins else 1
    lines = []
    for row in range(height - 1, -1, -1):
        threshold = (row + 1) / height * max_bin
        line = ""
        for b in bins:
            line += BAR_FULL if b >= threshold else " "
        lines.append("  " + DIM + line + RESET)
    lines.append("  " + DIM + "0x00" + " " * (width - 8) + "0xFF" + RESET)
    return lines


def main():
    capture_path = DEFAULT_CAPTURE
    if len(sys.argv) > 1 and sys.argv[1] != "--live":
        capture_path = Path(sys.argv[1])

    if not capture_path.exists():
        print(f"Capture file not found: {capture_path}")
        return 1

    text = capture_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.strip().split("\n") if "ST:" in line]

    if not lines:
        print("No data frames found in capture.")
        return 1

    frames = [parse_frame(line) for line in lines]
    frames = [f for f in frames if f]

    print(f"\n{BOLD}EMBER Silicon Visualization{RESET}")
    print(f"  Source: {capture_path.name}")
    print(f"  Frames: {len(frames)}")
    print()

    # --- 1. Topology rotation timeline ---
    print(f"{BOLD}1. XOR Topology Rotation Timeline{RESET}")
    print("   Each column = one frame. Color = active topology.")
    print()
    topo_timeline = []
    switch_events = []
    prev_topo = -1
    for i, f in enumerate(frames):
        tp = f.get("TP", 0)
        active = tp & 0x3
        (tp >> 2) & 0x3FFFFFFF
        topo_timeline.append(active)
        if active != prev_topo and prev_topo >= 0:
            switch_events.append((i, prev_topo, active))
        prev_topo = active

    # Render as colored blocks, 80 per row
    row_width = 80
    for row_start in range(0, len(topo_timeline), row_width):
        chunk = topo_timeline[row_start:row_start + row_width]
        line = "   "
        for t in chunk:
            color = TOPO_COLORS[t] if t < 4 else ""
            line += color + BAR_FULL + RESET
        print(line)
    print()
    print(f"   {TOPO_COLORS[0]}{BAR_FULL} concentric{RESET}  "
          f"{TOPO_COLORS[1]}{BAR_FULL} radial{RESET}  "
          f"{TOPO_COLORS[2]}{BAR_FULL} hot_row{RESET}  "
          f"{TOPO_COLORS[3]}{BAR_FULL} opposing{RESET}")
    print(f"   Topology switches: {len(switch_events)}")
    print()

    # --- 2. Entropy throughput curve ---
    print(f"{BOLD}2. Entropy Throughput{RESET}")
    ent_counts = [f.get("EC", 0) for f in frames]
    deltas = [ent_counts[i] - ent_counts[i - 1] for i in range(1, len(ent_counts)) if ent_counts[i] >= ent_counts[i - 1]]
    if deltas:
        max_delta = max(deltas)
        avg_delta = sum(deltas) / len(deltas)
        print(f"   Bytes/frame: avg={avg_delta:,.0f}  max={max_delta:,.0f}")
        # ASCII sparkline
        spark_width = min(len(deltas), 80)
        step = max(1, len(deltas) // spark_width)
        sampled = [deltas[i * step] for i in range(spark_width)]
        levels = " " + BAR_1_4 + BAR_HALF + BAR_7_8 + BAR_FULL
        line = "   "
        for d in sampled:
            idx = int(d / max(max_delta, 1) * (len(levels) - 1))
            idx = min(idx, len(levels) - 1)
            line += DIM + levels[idx] + RESET
        print(line)
    print()

    # --- 3. Ring frequency ---
    print(f"{BOLD}3. Ring Frequency{RESET}")
    freqs = [f.get("RF", 0) for f in frames]
    # Handle two's complement for negative values
    freqs_signed = [v if v < 0x80000000 else v - 0x100000000 for v in freqs]
    if freqs_signed:
        print(f"   Raw values: {freqs_signed[0]:,} ... {freqs_signed[-1]:,}")
        unique = len(set(freqs_signed))
        print(f"   Unique values: {unique}/{len(freqs_signed)}")
    print()

    # --- 4. Status summary ---
    print(f"{BOLD}4. Health Status{RESET}")
    last = frames[-1]
    st = last.get("ST", 0)
    warmed = bool(st & 1)
    aes_ready = bool(st & 2)
    apt_alarm = bool(st & 4)
    stuck = bool(st & 8)
    valid = bool(st & 16)
    print(f"   Warmed up:    {'YES' if warmed else 'NO'}")
    print(f"   AES ready:    {'YES' if aes_ready else 'NO'}")
    print(f"   APT alarm:    {'ALARM' if apt_alarm else 'clear'}")
    print(f"   Stuck detect: {'STUCK' if stuck else 'clear'}")
    print(f"   Entropy valid:{'YES' if valid else 'NO'}")
    print(f"   Stuck bitmap: 0x{last.get('SK', 0):02X}")
    tp = last.get("TP", 0)
    print(f"   Active topo:  {tp & 0x3} ({TOPO_NAMES[tp & 0x3]})")
    print(f"   Total switches: {(tp >> 2) & 0x3FFFFFFF}")
    print(f"   Total entropy: {last.get('EC', 0):,} bytes")
    print()

    # --- 5. Entropy byte histogram ---
    print(f"{BOLD}5. Entropy Byte Distribution{RESET}")
    en_values = [f.get("EN", 0) & 0xFF for f in frames]
    byte_counts = {}
    for v in en_values:
        byte_counts[v] = byte_counts.get(v, 0) + 1
    for line in render_histogram(byte_counts):
        print(line)
    print(f"   {len(en_values)} samples across {len(byte_counts)} unique byte values")
    print()

    # --- 6. Topology switch detail ---
    if switch_events:
        print(f"{BOLD}6. Topology Switch Events (first 20){RESET}")
        for i, (frame_idx, old, new) in enumerate(switch_events[:20]):
            old_name = TOPO_NAMES[old] if old < 4 else "?"
            new_name = TOPO_NAMES[new] if new < 4 else "?"
            ec = frames[frame_idx].get("EC", 0)
            print(f"   frame {frame_idx:4d}: {TOPO_COLORS[old]}{old_name:>11s}{RESET} -> {TOPO_COLORS[new]}{new_name:<11s}{RESET}  entropy={ec:,}")
        if len(switch_events) > 20:
            print(f"   ... {len(switch_events) - 20} more")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
