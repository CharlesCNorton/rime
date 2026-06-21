# Metastability τ Measurement — ECP5-25F

First published empirical upper bound on the metastability time constant τ for Lattice ECP5-25F TRELLIS_FF flip-flops.

## Result

**τ < 14–16 ps.**

20 billion samples over 25 minutes. 4 independent synchronizer chains × 7 stages. Zero synchronization failures. 150 ring oscillator frequency snapshots tracking thermal drift across the full run.

The bound range reflects uncertainty in the metastability event count: 14 ps using the measured beat frequency (1.24 MHz × 1500s = 1.86 billion events), 16 ps using the conservative setup/hold window estimate (78 million events).

A single synchronizer FF on ECP5 at any frequency the fabric supports has an MTBF measured in geological time. Two-stage synchronizers are cosmically redundant on this process.

## Method

### MTBF synchronizer chain

A synchronizer chain of 8 flip-flops samples a 127-stage ring oscillator. FF[0] is the metastable source — its setup/hold time is violated whenever a ring oscillator edge falls within the sampling window. FF[1] through FF[7] are synchronizer stages. A metastability failure at stage k means FF[k+1] captured a different value than what FF[k] held on the previous cycle — the metastable state at FF[k] had not resolved by the time FF[k+1] sampled it.

### PLL-tuned frequency matching

The ECP5's EHXPLLL hard PLL generates a 13.33 MHz system clock from the 50 MHz board oscillator (CLKI_DIV=15, CLKFB_DIV=4, CLKOP_DIV=44, VCO=587 MHz). The 127-stage ring oscillator runs at a frequency determined by LUT propagation delay and process variation. The frequency difference between the PLL output and the ring oscillator determines the metastability event rate.

### Ring frequency measurement

A 2-FF synchronizer captures the ring oscillator output on sys_clk, and a rising-edge detector counts transitions. The count is snapshot every 10 seconds into BRAM (150 snapshots over 25 minutes). The measured beat frequency is 1.2417 MHz mean, with a downward drift from 1.2427 MHz to 1.2407 MHz as the die reaches thermal equilibrium.

### τ derivation

The failure probability at each synchronizer stage follows:

    P_fail = f_data × t_setup × exp(-t_resolve / τ)

With zero failures in N metastability events:

    τ < t_clk_to_q / ln(N_events)

Using t_clk_to_q ≈ 300 ps (ECP5 LUT4 propagation delay as proxy):
- Conservative (setup/hold window estimate): N ≈ 78M → τ < 300/18.2 = 16.5 ps
- Measured beat frequency: N ≈ 1.86B → τ < 300/21.3 = 14.1 ps

### Thermal drift

The ring oscillator frequency dropped 2,060 Hz (0.13%) over 25 minutes, stabilizing after ~15 minutes. The τ bound applies across the full thermal transient from cold start to steady state, not at a single operating temperature.

### Prior approaches (same experiment, earlier iterations)

1. **Delay-line TDC** (results_delay_tdc.bin): 64-tap delay line measuring resolution time directly. All events in bin 0. Confirms τ < 300 ps but no finer resolution — the FF resolves before the signal reaches the first delay tap.

2. **Vernier TDC** (results_vernier.bin): Two delay lines with different tap delays. Zero disagreements. Same conclusion as the delay-line TDC.

3. **MTBF 2-billion-sample run** (results_raw.txt): Same methodology at 2B samples. Zero failures. τ < 17 ps. The deep run tightens this to 14–16 ps with 10x more samples and measured ring frequency.

## Hardware

- ECP5-25F (CABGA256) on IcePi Zero v1.3
- EHXPLLL hard PLL: CLKI_DIV=15, CLKFB_DIV=4, CLKOP_DIV=44 → 13.33 MHz sys_clk
- 127-stage ring oscillator (LUT4 inverter chain)
- 4 synchronizer chains tapping ring nodes 1, 32, 64, 96
- 8 flip-flops per chain (7 comparison pairs)
- 40-bit failure counters per pair
- 32-bit ring frequency counter with 150-entry BRAM snapshot buffer

## Resource Usage

- LUT4: 966 / 24,288 (3.9%)
- DP16KD: 1 / 56 (ring frequency snapshots)
- TRELLIS_FF: 404 / 24,288
- Fmax: 72 MHz (sys_clk 13.33 MHz)

## Results

### Failure counts

20,000,000,001 samples. All 28 failure counters (4 chains × 7 pairs) read zero.

### Ring oscillator frequency (150 snapshots, 10-second intervals)

| Metric | Value |
|--------|-------|
| First snapshot | 1,242,731 Hz |
| Last snapshot | 1,240,671 Hz |
| Mean | 1,241,706 Hz |
| Min | 1,240,110 Hz |
| Max | 1,243,455 Hz |
| Drift | −2,060 Hz over 25 min (0.13%) |

The frequency series shows a monotonic downward trend for the first ~15 minutes as the die heats up, then stabilizes. The ring oscillator slows as junction temperature increases — consistent with increased carrier scattering at higher temperatures.

```
python parse_results.py results_deep.txt
```

## Files

| File | Role |
|------|------|
| `top.sv` | Experiment HDL (PLL + ring oscillator + synchronizer chains + frequency counter) |
| `build.json` | nextpnr flags (--ignore-loops --timing-allow-fail) |
| `results_deep.txt` | Deep run: 20B samples, 150 frequency snapshots, zero failures |
| `results_raw.txt` | Earlier run: 2B samples, zero failures |
| `results_delay_tdc.bin` | Delay-line TDC attempt (all bin 0) |
| `results_vernier.bin` | Vernier TDC attempt (zero disagreements) |
| `parse_results.py` | Parser, τ bound calculation, frequency drift analysis |

## Reproducing

```
python icepi_helper.py build metastability --clean
python icepi_admin.py flash metastability
# wait ~25 minutes, capture UART at 115200 baud
python parse_results.py results_deep.txt
```

The experiment runs autonomously. The LED pattern shows progress: LED[3] = accumulating, LED[2] = PLL locked, LED[1:0] = progress counter (changes every ~375 seconds).

## Portability

The experiment uses 3.9% of the ECP5-25F. It fits on any ECP5 variant with a UART and a 50 MHz oscillator. Porting requires only pin constraint changes. The PLL parameters may need adjustment for different input clock frequencies — use `ecppll -i <freq> -o 13` to regenerate.
