# Ring Survey — Die Tomography, Whole-Die Delay, Coupled Oscillator Dynamics

Three ring oscillator experiments in one folder, sharing the same measurement infrastructure.

## Results

### 1. Die tomography (3,000 independent 5-stage rings)

3,000 independent ring oscillators placed across the ECP5-25F die. Each ring's frequency encodes the local LUT propagation delay and routing characteristics at its physical location.

| Metric | Value |
|--------|-------|
| Rings measured | 3,000 |
| Mean edge count (10ms window) | 31,831 |
| Min | 1,168 |
| Max | 61,132 |
| Range | 188% of mean |
| Coefficient of variation | ~50% |

The 188% range between fastest and slowest rings reflects combined process variation (transistor threshold voltage, oxide thickness) and routing variation (wire length differences between rings placed at different physical locations by the synthesizer). The distribution is the spatial signature of this specific ECP5 die.

### 2. Whole-die delay (1,001-stage ring)

One ring oscillator traversing 1,001 LUT inverter stages across a large fraction of the die.

| Metric | Value |
|--------|-------|
| Edge count (10ms) | 9,501 |
| Estimated period | ~2.1 us (aliased) |

The frequency encodes the mean LUT propagation delay across the entire routing path. This is a single-number summary of the die's speed — analogous to a process corner measurement but on a specific physical chip.

### 3. Coupled nested topology (500 small rings + 1,001-stage large ring with 20 XOR coupling points)

The large ring is XOR-coupled to 20 small rings at 50-stage intervals. Each coupling point injects the small ring's oscillation into the large ring's propagation path.

| Metric | Uncoupled | Coupled |
|--------|-----------|---------|
| Large ring edges/10ms | 9,501 | 8,663 |
| Small ring mean edges/10ms | 31,831 (N=3000) | 29,778 (N=500) |

The coupling slowed the large ring by 8.8% — each XOR gate adds propagation delay. The frequency difference between coupled and uncoupled configurations at each coupling point encodes the injection locking strength, which depends on the physical proximity and routing between the large and small rings at that location.

## Method

All three experiments use the same measurement engine: a multiplexed edge counter with a 12.5 MHz system clock. Each ring output is selected through a MUX, synchronized with a 2-FF synchronizer, edge-detected, and counted for a 10ms window (125,000 sys_clk cycles). Results are stored in BRAM and output over UART as hex CSV.

The edge counts are aliased — the rings oscillate at ~250 MHz but are sampled at 12.5 MHz. The absolute frequency cannot be determined from the aliased count alone, but relative variation between rings is preserved. Two rings with edge counts of 30,000 and 60,000 have a 2:1 frequency ratio regardless of aliasing.

## Resource Usage

| Config | LUTs | Fmax |
|--------|------|------|
| Uncoupled (3,000 small + 1 large) | 19,432 (80%) | 65 MHz |
| Coupled (500 small + 1 large + 20 XOR) | 4,558 (18%) | 100 MHz |

## Files

| File | Role |
|------|------|
| `top.sv` | Uncoupled: 3,000 small rings + 1 large ring |
| `top_coupled.sv` | Coupled: 500 small rings + 1 large ring with XOR coupling |
| `build.json` | nextpnr flags (--ignore-loops --timing-allow-fail) |
| `results_raw.txt` | Uncoupled run: 3,001 frequency measurements |
| `results_coupled.txt` | Coupled run: 501 frequency measurements |
| `parse_results.py` | Parser with statistics and histogram |

## Reproducing

Uncoupled (default):
```
python icepi_helper.py build ring-survey --clean
python icepi_admin.py flash ring-survey
# wait ~50 seconds, capture UART at 115200 baud
python parse_results.py results_raw.txt
```

Coupled (swap top modules):
```
mv top.sv top_uncoupled.sv && mv top_coupled.sv top.sv
python icepi_helper.py build ring-survey --clean
python icepi_admin.py flash ring-survey
# wait ~25 seconds
mv top.sv top_coupled.sv && mv top_uncoupled.sv top.sv
```
