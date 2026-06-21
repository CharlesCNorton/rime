# Concentric rectangles: nested rectangular frames of ring oscillators.
# nextpnr placement constraint script (runs inside nextpnr Python context).
# Part of the thermal-geometry experiment — see README.md.

bel_lookup = {}
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        bel_lookup[(loc.x, loc.y, loc.z)] = bel

tiles = [(35, 30), (33, 36), (38, 26), (35, 36), (40, 26), (31, 26), (31, 32), (31, 29), (39, 36), (31, 35), (45, 28), (37, 30), (45, 31), (45, 34), (27, 28), (37, 36), (27, 31), (41, 30), (33, 26), (41, 27), (41, 33), (27, 34), (35, 26), (35, 32), (41, 36), (27, 35), (32, 36), (39, 26), (31, 28), (31, 31), (45, 30), (37, 26), (31, 34), (36, 30), (27, 27), (45, 27), (34, 36), (45, 33), (27, 30), (37, 32), (45, 36), (36, 36), (41, 26), (41, 32), (27, 33), (41, 29), (32, 26), (41, 35), (27, 36), (35, 31), (38, 36), (31, 30), (40, 36), (34, 26), (31, 27), (31, 33), (45, 26), (31, 36), (36, 26), (36, 32), (45, 29), (37, 31), (45, 32), (27, 26), (27, 32), (45, 35), (27, 29), (41, 28), (41, 31), (41, 34)]

placed = 0
for name, cell in ctx.cells:
    if "gen_ring[" not in name or "gen_st[" not in name:
        continue
    ring_idx = int(name.split("gen_ring[")[1].split("]")[0])
    stage = int(name.split("gen_st[")[1].split("]")[0])
    if ring_idx < len(tiles):
        tx, ty = tiles[ring_idx]
        key = (tx, ty, stage * 4)
        if key in bel_lookup:
            ctx.bindBel(bel_lookup[key], cell, PlaceStrength.STRENGTH_LOCKED)
            placed += 1

print(f"{placed} / 350 constrained for 09_concentric_rect (extras float)")
