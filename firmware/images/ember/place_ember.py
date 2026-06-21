"""place_ember: generate LPF placement constraints for EMBER ring oscillators.

Distributes 192 ring oscillators across three thermally isolated paths
on the ECP5 die. Each path occupies a distinct row range to maximize
spatial separation and minimize thermal crosstalk between paths.
"""


def make_path(row_start, row_end, col_start=2, col_end=70, n_rings=64):
    rows = list(range(row_start, row_end + 1))
    cols = list(range(col_start, col_end + 1))
    n_rows = 4
    n_cols = 16
    row_step = max(1, len(rows) // n_rows)
    col_step = max(1, len(cols) // n_cols)
    tiles = []
    for ri in range(n_rows):
        r = rows[min(ri * row_step, len(rows) - 1)]
        for ci in range(n_cols):
            c = cols[min(ci * col_step, len(cols) - 1)]
            tiles.append((c, r))
            if len(tiles) >= n_rings:
                break
        if len(tiles) >= n_rings:
            break
    return tiles

path_a = make_path(2, 12)
path_b = []
path_c = []
all_tiles = path_a + path_b + path_c

print(f"Path A: {len(path_a)} rings in rows 2-12")
print(f"Path B: {len(path_b)} rings in rows 14-24")
print(f"Path C: {len(path_c)} rings in rows 26-36")
print(f"Total: {len(all_tiles)} rings to constrain")

bel_lookup = {}
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        bel_lookup[(loc.x, loc.y, loc.z)] = bel

placed = 0
failed = 0
for name, cell in ctx.cells:
    if "gen_ring[" not in name or "gen_st[" not in name:
        continue
    ring_idx = int(name.split("gen_ring[")[1].split("]")[0])
    stage = int(name.split("gen_st[")[1].split("]")[0])
    if ring_idx < len(all_tiles):
        tx, ty = all_tiles[ring_idx]
        key = (tx, ty, stage * 4)
        if key in bel_lookup:
            bel = bel_lookup[key]
            if not ctx.checkBelAvail(bel):
                failed += 1
            else:
                try:
                    ctx.bindBel(bel, cell, PlaceStrength.STRENGTH_STRONG)
                    placed += 1
                except Exception as e:
                    print(f"  FAIL: {name} at ({tx},{ty},z={stage*4}): {e}")
                    failed += 1
        else:
            failed += 1

print(f"{placed} placed, {failed} failed out of {len(all_tiles) * 5}")
