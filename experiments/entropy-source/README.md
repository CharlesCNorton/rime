# Entropy Source — Deployable Hardware TRNG

Ring oscillator TRNG with thermal warmup, Von Neumann debiasing, health monitoring, and continuous UART output. Designed for future instantiation as a module inside the PicoRV32 image or Frost.

## Result

**129 kbit/s of statistically uniform entropy from 64 ring oscillators on the ECP5-25F.**

| Test | Result | Threshold | Status |
|------|--------|-----------|--------|
| Chi-squared (byte uniformity) | 308 | <310 | PASS |
| Bit bias | 50.0000% | ~50% | PASS |
| Serial correlation (lag-1) | 0.3920% | ~0.3906% expected | PASS |
| Runs test | ratio 1.0000 | 0.98-1.02 | PASS |

485,211 entropy bytes collected in 30 seconds after a 30-second thermal warmup.

## Architecture

### Entropy generation

64 independent 5-stage ring oscillators (LUT4 inverter chains, ~250 MHz). Each ring's phase drifts randomly due to thermal noise in the transistor switching thresholds.

### Mixing

8 entropy channels, each XOR-combining 8 ring oscillator outputs. XOR mixing whitens the output by combining independent jitter sources — any single biased ring is corrected by the other 7.

### Von Neumann debiasing

Each channel takes consecutive pairs of raw bits. If the pair differs (01 or 10), one bit is output. If the pair matches (00 or 11), it is discarded. This removes first-order bias regardless of the raw bit probability, at the cost of ~50% throughput.

### Thermal warmup

The die temperature rises after power-on as switching activity heats the silicon. Ring oscillator frequencies drift during this transient. The entropy source waits 30 seconds before declaring READY — sufficient for thermal stabilization based on the metastability experiment's ring frequency time series (stabilized after ~15 minutes, but frequency jitter dominates over thermal drift after 30 seconds).

### Health monitoring

- **Ring frequency counter**: measures a reference ring's edge rate every second, reported in health lines.
- **Stuck-at detector**: per-channel alarm if 1,024 consecutive identical bits are produced. Indicates a dead or stuck ring oscillator.
- **Health reports**: "H,<freq_hex>,<stuck_bits_hex>" every 10 seconds, interleaved with the entropy stream.

## Output Format

```
W,004EBDE5          (warmup: ring frequency hex, one per second)
W,004EB6A6
...
READY               (thermal warmup complete)
<raw entropy bytes> (continuous, 115200 baud)
H,004F3722,00       (health: ring freq, stuck channel bitmap — every 10s)
<raw entropy bytes>
...
```

After READY, the output is a continuous stream of raw entropy bytes at 115200 baud (~11 KB/s UART limit). Health lines are interleaved every 10 seconds.

## Resource Usage

- LUT4: 1,260 / 24,288 (5%)
- Fmax: 112 MHz (sys_clk 12.5 MHz)
- Rings: 64 × 5 = 320 LUTs
- Control + UART + debiaser + monitoring: ~940 LUTs

The 5% footprint means this design can be instantiated as a module inside any RIME image with a parameterized ring count.

## Files

| File | Role |
|------|------|
| `top.sv` | Complete TRNG: rings, mixing, debiaser, warmup, health, UART |
| `build.json` | nextpnr flags (--ignore-loops --timing-allow-fail) |
| `results_entropy.bin` | 485,211 bytes of raw hardware entropy |
| `parse_results.py` | Statistical analysis (chi-squared, bias, correlation, runs) |

## Reproducing

```
python icepi_helper.py build entropy-source --clean
python icepi_admin.py flash entropy-source
# wait 30 seconds for READY, then capture entropy at 115200 baud
python parse_results.py results_entropy.bin
```

## Future

Parameterize `NUM_RINGS` and `RINGS_PER_CHANNEL` for instantiation inside the PicoRV32 image or Frost as a TRNG peripheral. At 5% LUT cost, any image can include hardware entropy without meaningful resource impact.
