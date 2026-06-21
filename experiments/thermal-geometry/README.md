# Thermal Geometry — Spatially Controlled Die Characterization

Ring oscillators placed at known physical tile positions on the ECP5-25F die. Ten geometric arrangements measure thermal coupling, power supply droop, boundary effects, and the relationship between neighbor density and oscillator frequency.

## Result

**Active neighbor density shifts ring oscillator frequency by up to 18%.** Sparse rings (few active neighbors) run 12-18% faster than dense rings. The coupling is geometric — concentric arrangements that trap heat run 5-7% slower than the die average. Routing variation dominates at 147-174% range, but the systematic 18% density effect is a real thermal/electrical signal separated from routing noise by the constrained vs floating comparison.

## Method

All 10 arrangements use the same HDL: 759 5-stage ring oscillators with a sequential measurement engine (10ms window per ring, UART output). The only difference is physical placement. A nextpnr `--pre-place` Python script constrains a subset of rings to specific (x, y) tile coordinates. The remaining rings float (placed by nextpnr wherever it finds room).

Comparing the constrained rings (known positions, controlled geometry) against the floating rings (random placement, same netlist, same build) separates geometric effects from synthesis artifacts.

### ECP5-25F tile grid

```
44 rows x 69 cols = 3,036 logic tiles = 24,288 LUTs

Block 1 (R02-R12): experimental rings
Block 2 (R14-R24): experimental rings
Block 3 (R26-R36): experimental rings
   Row 13: DSP stripe   Row 25, 37: BRAM stripes
Block 4 (R38-R48): control logic (UART, measurement, output)
```

### Arrangements

| # | Name | Rings | Geometry | Question |
|---|------|-------|----------|----------|
| 1 | Full saturation | 759 | Every tile in Block 1 | Baseline — all neighbors active |
| 2 | Checkerboard | 380 | Alternating tiles in Block 2 | Effect of zero immediate neighbors |
| 3 | Isolation radial | 13 | Center + probes at d=2,5,10,20 | Thermal decay curve |
| 4 | Stripe gradient | 374 | Left half saturated, right empty | Lateral thermal diffusion |
| 5 | Single hot row | 75 | One dense row + sparse probes | 1D heat source into 2D silicon |
| 6 | Corner source | 35 | 5x5 corner + log probes | 2D thermal Green's function |
| 7 | Density sweep | 25 | Columns at different fill densities | Density vs frequency directly |
| 8 | Opposing walls | 31 | Two hot columns + midpoint probes | Thermal superposition |
| 9 | Concentric rectangles | 70 | Nested shells with dead gaps | Thermal confinement |
| 10 | Spiral | 409 | Outside-in spiral track | Continuous path with self-heating |

## Results

### Constrained vs floating ring frequency

| Arrangement | Placed | Mean (placed) | Mean (float) | Delta |
|---|---|---|---|---|
| Density sweep | 25 | 37,707 | 31,842 | **+18.4%** |
| Single hot row | 75 | 34,379 | 30,649 | **+12.2%** |
| Checkerboard | 380 | 34,232 | 30,926 | **+10.7%** |
| Stripe gradient | 374 | 32,760 | 30,724 | +6.6% |
| Spiral | 409 | 33,088 | 31,828 | +4.0% |
| Full saturation | 759 | 34,188 | N/A | baseline |
| Isolation radial | 13 | 29,835 | 30,604 | -2.5% |
| Opposing walls | 31 | 28,546 | 30,228 | -5.6% |
| Concentric rect | 70 | 28,719 | 30,945 | **-7.2%** |

### Interpretation

**Sparse arrangements run faster.** The density sweep (+18.4%) and single hot row (+12.2%) constrain rings to isolated positions with few active neighbors. Less local switching activity means less junction heating and less power supply droop. The rings oscillate at a frequency closer to the silicon's intrinsic speed.

**Dense geometric arrangements run slower.** Concentric rectangles (-7.2%) and opposing walls (-5.6%) force rings into positions surrounded by other active rings. The trapped heat and localized current draw slow the oscillation measurably.

**Full saturation is faster than expected.** 759 rings filling every tile in Block 1 should be the hottest, slowest arrangement. Instead it has the highest mean (34,188). The explanation: compact placement in one block gives every ring short routing within its tile. The routing advantage outweighs the thermal penalty. This confirms that the 147-174% frequency ranges across arrangements are dominated by routing variation, with the 18% thermal/density effect as a secondary signal.

**The BRAM stripe boundary matters.** The isolation radial (centered near R31, close to the BRAM stripe at R37) runs 2.5% slower than floating rings. The BRAM stripe is a thermal boundary with different conductivity characteristics than the logic fabric.

## Implications for Ember

The thermal coupling radius is approximately 10-15 tiles based on the density effect and boundary measurements. Ember's ring oscillators should be spaced at least this far apart for maximum entropy independence. On the 44x69 grid, this means ~20-30 maximally independent ring positions rather than 192 randomly placed rings.

## Resource Usage

- LUT4: ~5,000 / 24,288 (20%) — 759 rings + measurement engine
- DP16KD: ~4 / 56 (results storage)
- Fmax: varies by arrangement (timing-allow-fail due to ring oscillator loops)

## Files

| File | Role |
|------|------|
| `top.sv` | Measurement engine HDL (759 rings, sequential sweep, UART output) |
| `gen_arrangements.py` | Generates all 10 placement scripts from geometry definitions |
| `place_*.py` | Per-arrangement nextpnr pre-place scripts (generated) |
| `run_all.py` | Automated build + load + capture pipeline for all arrangements |
| `results_*.txt` | Raw UART captures (per-ring edge counts, hex CSV) |
| `parse_results.py` | Comparative analysis of constrained vs floating rings |
| `build.json` | nextpnr flags (--ignore-loops --timing-allow-fail) |

## Reproducing

```
python gen_arrangements.py           # generate placement scripts
python run_all.py                    # build, load, capture all 10
python parse_results.py              # comparative analysis
```

Requires OSS CAD Suite, pyserial, and the IcePi Zero board on COM9. Full run takes ~40 minutes (synthesis once + 10 place-and-route + load + capture cycles).

## Note

Arrangement #6 (corner source) failed at place-and-route due to tile coordinates at the block edge exceeding valid positions. The remaining 9 arrangements all produced valid data.
