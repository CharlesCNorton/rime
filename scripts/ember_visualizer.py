#!/usr/bin/env python3
"""EMBER state visualizer — scientific instrument display.

Every visual element maps to a real data field from silicon.

Die map: 192 rings in 3 quadrants. Color = XOR channel (0-7).
Throughput graph: conditioned bytes per frame over time.
Topology strip: which topology was active at each frame.
Random number: 64-bit conditioned entropy, updated every frame.

Usage:
    python scripts/ember_visualizer.py                          # replay capture
    python scripts/ember_visualizer.py --live COM837            # live from board
    python scripts/ember_visualizer.py path/to/capture.txt      # replay file
"""

import json
import sys
from pathlib import Path

import pygame

DEFAULT_CAPTURE = Path(__file__).resolve().parent.parent / "modules" / "compositions" / "ember_direct_capture.txt"
TOPO_FILE = Path(__file__).resolve().parent.parent / "modules" / "ember" / "xor_topologies.json"

W, H = 1280, 800
FPS = 30
DATA_FPS = 4  # advance one data frame every 250ms — matches real-time capture rate

TOPO_NAMES = ["concentric", "radial", "hot row", "opposing"]

# 8 XOR channel colors — distinct, readable on dark background
CH_COLORS = [
    (0, 180, 220),    # 0: teal
    (220, 80, 220),   # 1: purple
    (80, 200, 80),    # 2: green
    (220, 200, 60),   # 3: yellow
    (220, 120, 40),   # 4: orange
    (80, 120, 240),   # 5: blue
    (220, 70, 70),    # 6: red
    (180, 180, 180),  # 7: gray
]

TOPO_COLORS = [
    (0, 160, 220),    # concentric
    (220, 180, 0),    # radial
    (0, 200, 100),    # hot row
    (220, 60, 60),    # opposing
]

BG = (18, 18, 24)
PANEL_BG = (26, 26, 34)
GRID = (40, 40, 50)
TEXT_DIM = (100, 100, 110)
TEXT_MID = (160, 160, 170)
TEXT_HI = (220, 220, 230)


def parse_line(line):
    """Parse one data line into a dict. RN field kept as hex string."""
    if "ST:" not in line:
        return None
    fields = {}
    for part in line.strip().split(","):
        if ":" in part:
            tag, val = part.split(":", 1)
            tag = tag.strip()
            val = val.strip()
            if tag == "RN":
                fields["RN"] = val  # keep as hex string
            else:
                try:
                    fields[tag] = int(val, 16)
                except ValueError:
                    pass
    return fields if fields else None


def parse_capture(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    frames = []
    for line in text.strip().split("\n"):
        f = parse_line(line)
        if f:
            frames.append(f)
    return frames


def load_topologies():
    if not TOPO_FILE.exists():
        return [[i % 8 for i in range(192)] for _ in range(4)]
    data = json.loads(TOPO_FILE.read_text())
    keys = ["concentric_rect", "isolation_radial", "single_hot_row", "opposing_walls"]
    result = []
    for tname in keys:
        words = data[tname]
        channels = []
        for ri in range(192):
            wi, bi = ri // 10, ri % 10
            channels.append((words[wi] >> (bi * 3)) & 0x7)
        result.append(channels)
    return result


def main():
    live_port = None
    capture_path = DEFAULT_CAPTURE

    if len(sys.argv) > 1:
        if sys.argv[1] == "--live" and len(sys.argv) > 2:
            live_port = sys.argv[2]
        else:
            capture_path = Path(sys.argv[1])

    if live_port:
        import serial
        ser = serial.Serial(live_port, 115200, timeout=0.05)
        ser.reset_input_buffer()
        frames = []
        print(f"Live: {live_port} (waiting for data...)")
    else:
        ser = None
        if not capture_path.exists():
            print(f"Not found: {capture_path}")
            return 1
        frames = parse_capture(capture_path)
        if not frames:
            print("No frames")
            return 1

    ring_channels = load_topologies()

    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("EMBER")
    clock = pygame.time.Clock()
    fn = pygame.font.SysFont("consolas", 13)
    fn_mid = pygame.font.SysFont("consolas", 16)
    fn_big = pygame.font.SysFont("consolas", 22)
    fn_label = pygame.font.SysFont("consolas", 11)

    # Layout constants
    DIE_X, DIE_Y = 30, 60
    DIE_W, DIE_H = 560, 520
    QUAD_PAD = 16
    RING_R = 7

    PANEL_X = 620
    PANEL_W = W - PANEL_X - 20

    # Precompute ring positions (3 quadrants of 64 rings, 8x8 grid each)
    qw = (DIE_W - QUAD_PAD * 3) // 2
    qh = (DIE_H - QUAD_PAD * 3) // 2
    quads = [
        (DIE_X + QUAD_PAD, DIE_Y + QUAD_PAD),                    # A: top-left
        (DIE_X + QUAD_PAD + qw + QUAD_PAD, DIE_Y + QUAD_PAD),    # B: top-right
        (DIE_X + QUAD_PAD, DIE_Y + QUAD_PAD + qh + QUAD_PAD),    # C: bottom-left
    ]
    positions = []
    for qi, (qx, qy) in enumerate(quads):
        for ri in range(64):
            r, c = ri // 8, ri % 8
            x = qx + int((c + 0.5) / 8 * qw)
            y = qy + int((r + 0.5) / 8 * qh)
            positions.append((x, y, qi))

    # Throughput history
    throughput_hist = []
    topo_hist = []

    frame_idx = 0
    data_accum = 0.0  # accumulates time to advance data frames
    prev_topo = -1
    blend_t = 1.0  # 0..1 blend from previous to current topology colors
    prev_channels = ring_channels[0]
    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        data_accum += dt * DATA_FPS

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    frame_idx = 0
                    throughput_hist.clear()
                    topo_hist.clear()

        # Live serial: read lines and append new frames
        if ser is not None:
            try:
                raw = ser.readline()
                if raw:
                    line = raw.decode("ascii", errors="replace").strip()
                    f_new = parse_line(line)
                    if f_new:
                        frames.append(f_new)
                        frame_idx = len(frames) - 1
            except Exception:
                pass
        else:
            # Replay: advance data frames at DATA_FPS rate
            if data_accum >= 1.0:
                steps = int(data_accum)
                frame_idx += steps
                data_accum -= steps

        if not frames:
            screen.fill(BG)
            msg = fn_big.render("Waiting for EMBER warmup (60s)...", True, TEXT_MID)
            screen.blit(msg, (W // 2 - msg.get_width() // 2, H // 2))
            pygame.display.flip()
            continue

        f = frames[frame_idx % len(frames)]
        tp_raw = f.get("TP", 0)
        active_topo = tp_raw & 0x3
        switch_count = (tp_raw >> 2) & 0x3FFFFFFF
        ent_count = f.get("EC", 0)
        status = f.get("ST", 0)
        f.get("EN", 0) & 0xFF
        stuck = f.get("SK", 0)
        f.get("RF", 0)

        # Throughput delta
        if frame_idx > 0:
            prev_ec = frames[(frame_idx - 1) % len(frames)].get("EC", 0)
            delta = ent_count - prev_ec if ent_count >= prev_ec else 0
        else:
            delta = 0
        throughput_hist.append(delta)
        topo_hist.append(active_topo)
        if len(throughput_hist) > 400:
            throughput_hist.pop(0)
            topo_hist.pop(0)

        channels = ring_channels[active_topo]

        # Smooth topology transition: blend over 0.5 seconds
        if active_topo != prev_topo and prev_topo >= 0:
            prev_channels = ring_channels[prev_topo]
            blend_t = 0.0
        prev_topo = active_topo
        blend_t = min(1.0, blend_t + dt * 2.0)  # 0.5 second blend

        # --- Draw ---
        screen.fill(BG)

        # Die outline
        pygame.draw.rect(screen, GRID, (DIE_X, DIE_Y, DIE_W, DIE_H), 1)

        # Quadrant labels
        q_names = ["Path A (top-left)", "Path B (top-right)", "Path C (bottom-left)"]
        for qi, (qx, qy) in enumerate(quads):
            pygame.draw.rect(screen, (30, 30, 40), (qx - 2, qy - 2, qw + 4, qh + 4), 1)
            lbl = fn_label.render(q_names[qi], True, TEXT_DIM)
            screen.blit(lbl, (qx, qy - 14))

        # CPU quadrant (bottom-right, empty)
        cpu_x = DIE_X + QUAD_PAD + qw + QUAD_PAD
        cpu_y = DIE_Y + QUAD_PAD + qh + QUAD_PAD
        pygame.draw.rect(screen, (30, 30, 40), (cpu_x - 2, cpu_y - 2, qw + 4, qh + 4), 1)
        lbl = fn_mid.render("RIME-I", True, TEXT_DIM)
        screen.blit(lbl, (cpu_x + qw // 2 - lbl.get_width() // 2, cpu_y + qh // 2 - 10))
        lbl2 = fn_label.render("(computation quadrant)", True, (60, 60, 70))
        screen.blit(lbl2, (cpu_x + qw // 2 - lbl2.get_width() // 2, cpu_y + qh // 2 + 10))

        # Ring oscillators — color = channel assignment, blended during transitions
        for ri, (rx, ry, qi) in enumerate(positions):
            ch_new = channels[ri]
            c_new = CH_COLORS[ch_new]
            if blend_t < 1.0:
                ch_old = prev_channels[ri]
                c_old = CH_COLORS[ch_old]
                color = tuple(int(c_old[i] + (c_new[i] - c_old[i]) * blend_t) for i in range(3))
            else:
                color = c_new
            pygame.draw.circle(screen, color, (rx, ry), RING_R)
            pygame.draw.circle(screen, (10, 10, 14), (rx, ry), RING_R, 1)

        # Title
        title = fn_big.render("EMBER", True, TOPO_COLORS[active_topo])
        screen.blit(title, (DIE_X, 20))
        topo_label = fn_mid.render(f"topology: {TOPO_NAMES[active_topo]}", True, TOPO_COLORS[active_topo])
        screen.blit(topo_label, (DIE_X + title.get_width() + 20, 24))

        # --- Right panel ---
        px = PANEL_X
        py = 60

        # Channel legend
        hdr = fn_mid.render("XOR channels", True, TEXT_HI)
        screen.blit(hdr, (px, py))
        py += 24
        for ci in range(8):
            count = sum(1 for c in channels if c == ci)
            pygame.draw.circle(screen, CH_COLORS[ci], (px + 8, py + 7), 5)
            lbl = fn.render(f"ch{ci}: {count} rings", True, TEXT_MID)
            screen.blit(lbl, (px + 20, py))
            py += 18
        py += 12

        # Status
        hdr = fn_mid.render("Health", True, TEXT_HI)
        screen.blit(hdr, (px, py))
        py += 22
        warmed = bool(status & 1)
        aes_ok = bool(status & 2)
        apt_alarm = bool(status & 4)
        bool(status & 8)
        ent_valid = bool(status & 16)
        for label, val, good in [
            ("warmed up", warmed, warmed),
            ("AES ready", aes_ok, aes_ok),
            ("APT", "clear" if not apt_alarm else "ALARM", not apt_alarm),
            ("stuck", f"0x{stuck:02X}" if stuck else "none", stuck == 0),
            ("entropy", "valid" if ent_valid else "---", ent_valid),
        ]:
            color = (80, 200, 100) if good else (220, 70, 70)
            dot = fn.render("\u25CF", True, color)
            screen.blit(dot, (px, py))
            txt = fn.render(f" {label}: {val}", True, TEXT_MID)
            screen.blit(txt, (px + 14, py))
            py += 18
        py += 12

        # Random number (the point of the whole system)
        rn_str = f.get("RN", "")
        if rn_str:
            hdr = fn_mid.render("Random number", True, TEXT_HI)
            screen.blit(hdr, (px, py))
            py += 22
            rn_surf = fn_big.render(rn_str, True, (0, 255, 200))
            screen.blit(rn_surf, (px, py))
            py += 30
        else:
            py += 10

        # Entropy count
        hdr = fn_mid.render("Total entropy", True, TEXT_HI)
        screen.blit(hdr, (px, py))
        py += 22
        ent_surf = fn_mid.render(f"{ent_count:,} bytes", True, (0, 200, 255))
        screen.blit(ent_surf, (px, py))
        py += 22
        if delta > 0:
            rate_str = f"+{delta:,}/frame"
            rate_surf = fn.render(rate_str, True, TEXT_DIM)
            screen.blit(rate_surf, (px, py))
        py += 18

        # Counters
        for label, val in [
            ("topo switches", f"{switch_count:,}"),
            ("active topo", f"{TOPO_NAMES[active_topo]}"),
            ("frame", f"{frame_idx}/{len(frames)}"),
        ]:
            txt = fn.render(f"{label}: {val}", True, TEXT_DIM)
            screen.blit(txt, (px, py))
            py += 16
        py += 12

        # Throughput graph
        graph_x, graph_y = px, py
        graph_w, graph_h = PANEL_W, 120
        hdr = fn_mid.render("Throughput (bytes/frame)", True, TEXT_HI)
        screen.blit(hdr, (graph_x, graph_y))
        graph_y += 22
        pygame.draw.rect(screen, PANEL_BG, (graph_x, graph_y, graph_w, graph_h))
        pygame.draw.rect(screen, GRID, (graph_x, graph_y, graph_w, graph_h), 1)

        if len(throughput_hist) > 1:
            max_tp = max(throughput_hist) or 1
            points = []
            for i, tp in enumerate(throughput_hist):
                x = graph_x + int(i / max(len(throughput_hist) - 1, 1) * (graph_w - 1))
                y = graph_y + graph_h - 1 - int(tp / max_tp * (graph_h - 4))
                points.append((x, y))
            if len(points) > 1:
                pygame.draw.lines(screen, (0, 180, 220), False, points, 1)
            # Scale label
            lbl = fn_label.render(f"{max_tp:,}", True, TEXT_DIM)
            screen.blit(lbl, (graph_x + 4, graph_y + 2))
        py = graph_y + graph_h + 12

        # Topology timeline strip
        strip_x, strip_y = px, py
        strip_w, strip_h = PANEL_W, 30
        hdr = fn_mid.render("Topology timeline", True, TEXT_HI)
        screen.blit(hdr, (strip_x, strip_y))
        strip_y += 20
        pygame.draw.rect(screen, PANEL_BG, (strip_x, strip_y, strip_w, strip_h))

        if topo_hist:
            col_w = max(1, strip_w / len(topo_hist))
            for i, t in enumerate(topo_hist):
                x = strip_x + int(i * col_w)
                w = max(1, int(col_w) + 1)
                pygame.draw.rect(screen, TOPO_COLORS[t], (x, strip_y, w, strip_h))

        # Topology legend below strip
        ly = strip_y + strip_h + 4
        lx = strip_x
        for ti in range(4):
            pygame.draw.rect(screen, TOPO_COLORS[ti], (lx, ly, 10, 10))
            lbl = fn_label.render(TOPO_NAMES[ti], True, TEXT_DIM)
            screen.blit(lbl, (lx + 14, ly - 1))
            lx += 14 + lbl.get_width() + 12

        pygame.display.flip()
        frame_idx += 1
        if frame_idx >= len(frames):
            frame_idx = 0

    pygame.quit()
    if ser is not None:
        ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
