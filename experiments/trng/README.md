# TRNG — Hardware True Random Number Generator

Ring oscillator phase jitter sampled on the ECP5-25F.

## Method

A 5-stage ring oscillator (~300 MHz) runs asynchronously to the 12.5 MHz system clock. Eight flip-flops sample different ring taps on each sys_clk edge. The sampled signal propagates through a 64-tap delay line (~300 ps/tap). A transition detector finds where the captured delay line value changes — this encodes the ring oscillator's phase relative to sys_clk at ~300 ps resolution.

The phase has no deterministic relationship to sys_clk because the ring oscillator frequency is set by LUT propagation delay and routing, which depend on thermal noise and process variation. Each sample produces a 6-bit physically random value.

## Hardware

- 8 independent channels (decorrelated by tapping different ring nodes)
- 64-tap delay lines per channel (LUT4 buffer chains)
- 10 million accumulation rounds per channel
- Histogram: 512 bins (8 channels × 64 bins), 24-bit counters
- UART output: hex CSV

## Results

Uniform distribution across all 64 bins on all 8 channels. The per-bin count varies by less than 1% from the mean, consistent with a physically random phase source.

```
python parse_results.py results_raw.bin
```

## Resource Usage

- LUT4: ~4,200 / 24,288 (17%)
- DP16KD: 1 / 56
- Fmax: 22 MHz (sys_clk 12.5 MHz)

## Files

- `top.sv` — experiment HDL
- `build.json` — nextpnr flags (--ignore-loops --timing-allow-fail for ring oscillator)
- `results_raw.bin` — raw UART capture from hardware run
- `parse_results.py` — parser and uniformity analysis
