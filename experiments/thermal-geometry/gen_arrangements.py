#!/usr/bin/env python3
"""Generate nextpnr pre-place scripts for all 10 thermal geometry arrangements.

Each arrangement defines which (x, y) tiles get rings.  The pre-place
script maps gen_ring[N].gen_st[M].inv to tile (x, y) with z = M*4.

ECP5-25F logic tile grid:
  Block 1: rows 2-12,  cols 2-70  (11 × 69 = 759 tiles)
  Block 2: rows 14-24, cols 2-70  (11 × 69 = 759 tiles)
  Block 3: rows 26-36, cols 2-70  (11 × 69 = 759 tiles)
  Block 4: rows 38-48, cols 2-70  (control logic, not for rings)
  Row 13 = DSP, Row 25 = BRAM, Row 37 = BRAM
"""

import os


BLOCK1_ROWS = range(2, 13)
BLOCK2_ROWS = range(14, 25)
BLOCK3_ROWS = range(26, 37)
COLS = range(2, 71)

def gen_preplace(name, tiles, out_dir):
    """Generate a pre-place Python script for the given tile list."""
    path = os.path.join(out_dir, f"place_{name}.py")
    with open(path, "w") as f:
        f.write(f'# Pre-place script for arrangement: {name}\n')
        f.write(f'# {len(tiles)} rings\n\n')
        f.write('bel_lookup = {}\n')
        f.write('for bel in ctx.getBels():\n')
        f.write('    if "COMB" in str(ctx.getBelType(bel)):\n')
        f.write('        loc = ctx.getBelLocation(bel)\n')
        f.write('        bel_lookup[(loc.x, loc.y, loc.z)] = bel\n\n')
        f.write(f'tiles = {tiles}\n\n')
        f.write('# Only constrain rings in the arrangement, let extras float\n')
        f.write('placed = 0\n')
        f.write('for name, cell in ctx.cells:\n')
        f.write('    if "gen_ring[" not in name or "gen_st[" not in name:\n')
        f.write('        continue\n')
        f.write('    ring_idx = int(name.split("gen_ring[")[1].split("]")[0])\n')
        f.write('    stage = int(name.split("gen_st[")[1].split("]")[0])\n')
        f.write('    if ring_idx < len(tiles):\n')
        f.write('        tx, ty = tiles[ring_idx]\n')
        f.write('        key = (tx, ty, stage * 4)\n')
        f.write('        if key in bel_lookup:\n')
        f.write('            ctx.bindBel(bel_lookup[key], cell, PlaceStrength.STRENGTH_LOCKED)\n')
        f.write('            placed += 1\n\n')
        f.write(f'print(f"{{placed}} / {len(tiles)*5} constrained for {name} (extras float)")\n')
    return path, len(tiles)


def arrangement_1_full_saturation():
    """Block 1: every tile."""
    tiles = [(x, y) for y in BLOCK1_ROWS for x in COLS]
    return tiles

def arrangement_2_checkerboard():
    """Block 2: alternating tiles."""
    tiles = [(x, y) for y in BLOCK2_ROWS for x in COLS if (x + y) % 2 == 0]
    return tiles

def arrangement_3_isolation_radial():
    """Block 3: center + rings at distances 2, 5, 10, 20."""
    cx, cy = 36, 31
    tiles = [(cx, cy)]
    for d in [2, 5, 10, 20]:
        for dx, dy in [(d, 0), (-d, 0), (0, d), (0, -d)]:
            nx, ny = cx + dx, cy + dy
            if 2 <= nx <= 70 and 26 <= ny <= 36:
                tiles.append((nx, ny))
    return tiles

def arrangement_4_stripe_gradient():
    """Block 1: left half saturated, right half empty."""
    tiles = [(x, y) for y in BLOCK1_ROWS for x in range(2, 36)]
    return tiles

def arrangement_5_single_hot_row():
    """Block 2: one row fully saturated, probe rows above and below."""
    hot_row = 19
    tiles = [(x, hot_row) for x in COLS]
    for d in [1, 2, 4]:
        for sign in [-1, 1]:
            py = hot_row + d * sign
            if 14 <= py <= 24:
                tiles.append((36, py))
    return tiles

def arrangement_6_corner_source():
    """Block 3: 5×5 corner + logarithmic probes."""
    tiles = [(x, y) for y in range(26, 31) for x in range(2, 7)]
    for d in [8, 15, 25, 35, 50]:
        nx = 2 + d
        if 2 <= nx <= 70:
            tiles.append((nx, 26))
        ny = 26 + min(d, 10)
        if 26 <= ny <= 36:
            tiles.append((2, ny))
    return tiles

def arrangement_7_density_sweep():
    """Block 1: columns at different densities."""
    tiles = []
    for y in BLOCK1_ROWS:
        tiles.append((5, y))
    for y in list(BLOCK1_ROWS)[::2]:
        tiles.append((15, y))
    for y in list(BLOCK1_ROWS)[::3]:
        tiles.append((25, y))
    for y in list(BLOCK1_ROWS)[::4]:
        tiles.append((40, y))
    tiles.append((55, 7))
    return tiles

def arrangement_8_opposing_walls():
    """Block 2: two vertical hot walls + midpoint probes."""
    tiles = []
    for y in BLOCK2_ROWS:
        tiles.append((5, y))
        tiles.append((65, y))
    for x in [20, 36, 50]:
        for y in [17, 19, 21]:
            tiles.append((x, y))
    return tiles

def arrangement_9_concentric_rectangles():
    """Block 3: concentric rectangles with dead gaps."""
    cx, cy = 36, 31
    tiles = []
    for shell in range(6):
        d = shell * 2 + 1
        if shell % 2 == 0:
            for x in range(cx - d, cx + d + 1):
                for y in [cy - d, cy + d]:
                    if 2 <= x <= 70 and 26 <= y <= 36:
                        tiles.append((x, y))
            for y in range(cy - d + 1, cy + d):
                for x in [cx - d, cx + d]:
                    if 2 <= x <= 70 and 26 <= y <= 36:
                        tiles.append((x, y))
    return list(set(tiles))

def arrangement_10_spiral():
    """Block 1: spiral from outside to center."""
    tiles = []
    min_x, max_x = 2, 70
    min_y, max_y = 2, 12
    x, y = min_x, min_y
    _dx, _dy = 1, 0
    while min_x <= max_x and min_y <= max_y:
        for x in range(min_x, max_x + 1):
            tiles.append((x, min_y))
        min_y += 2
        for y in range(min_y, max_y + 1):
            tiles.append((max_x, y))
        max_x -= 2
        if min_y <= max_y:
            for x in range(max_x, min_x - 1, -1):
                tiles.append((x, max_y))
            max_y -= 2
        if min_x <= max_x:
            for y in range(max_y, min_y - 1, -1):
                tiles.append((min_x, y))
            min_x += 2
    return list(dict.fromkeys(tiles))


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))

    arrangements = [
        ("01_full_saturation", arrangement_1_full_saturation),
        ("02_checkerboard", arrangement_2_checkerboard),
        ("03_isolation_radial", arrangement_3_isolation_radial),
        ("04_stripe_gradient", arrangement_4_stripe_gradient),
        ("05_single_hot_row", arrangement_5_single_hot_row),
        ("06_corner_source", arrangement_6_corner_source),
        ("07_density_sweep", arrangement_7_density_sweep),
        ("08_opposing_walls", arrangement_8_opposing_walls),
        ("09_concentric_rect", arrangement_9_concentric_rectangles),
        ("10_spiral", arrangement_10_spiral),
    ]

    for name, gen_fn in arrangements:
        tiles = gen_fn()
        path, count = gen_preplace(name, tiles, out_dir)
        print(f"{name:25s}  {count:>5} rings  {count*5:>5} LUTs  -> {os.path.basename(path)}")
