# Radial isolation: rings placed in concentric shells from die center.
# nextpnr placement constraint script (runs inside nextpnr Python context).
# Part of the thermal-geometry experiment — see README.md.

bel_lookup = {}
for bel in ctx.getBels():
    if "COMB" in str(ctx.getBelType(bel)):
        loc = ctx.getBelLocation(bel)
        bel_lookup[(loc.x, loc.y, loc.z)] = bel

tiles = [(36, 31), (38, 31), (34, 31), (36, 33), (36, 29), (41, 31), (31, 31), (36, 36), (36, 26), (46, 31), (26, 31), (56, 31), (16, 31)]

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

print(f"{placed} / 65 constrained for 03_isolation_radial (extras float)")
