# Corner source: rings clustered in one die corner to observe thermal gradient.
# nextpnr placement constraint script (runs inside nextpnr Python context).
# Part of the thermal-geometry experiment — see README.md.

bel_lookup = {}
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        bel_lookup[(loc.x, loc.y, loc.z)] = bel

tiles = [(2, 26), (3, 26), (4, 26), (5, 26), (6, 26), (2, 27), (3, 27), (4, 27), (5, 27), (6, 27), (2, 28), (3, 28), (4, 28), (5, 28), (6, 28), (2, 29), (3, 29), (4, 29), (5, 29), (6, 29), (2, 30), (3, 30), (4, 30), (5, 30), (6, 30), (10, 26), (2, 34), (17, 26), (2, 36), (27, 26), (2, 36), (37, 26), (2, 36), (52, 26), (2, 36)]

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

print(f"{placed} / 175 constrained for 06_corner_source (extras float)")
