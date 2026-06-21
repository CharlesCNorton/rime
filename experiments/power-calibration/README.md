# Power Calibration — Self-Contained Thermal Tomography

Measures per-cell-type dynamic power on ECP5-25F by using the FPGA die as both heat source and thermometer. No external measurement hardware required.

## Result

Per-cell-type dynamic power coefficients derived from spatial thermal profiles, calibrated against Lattice published data via correction factor from ring oscillator frequency measurements.

## Method

The die is instrumented with 4 workload zones (500 LUT4s each, toggling at CLK/2) at die corners, and 8 ring oscillator temperature sensors at known positions (zone centers + inter-zone midpoints + die center). Placement constraints (LPF LOCATE) fix all positions.

An 8-phase sweep activates different zone combinations: idle, single zones, zone pairs, all active. Between phases, 30 seconds of thermal settling. During measurement, ring oscillator frequencies are counted over a 0.5s window. DTR provides absolute temperature reference.

Ring oscillator frequency decreases linearly with temperature: `f(T) = f_ref × (1 - α × ΔT)` where α ≈ 0.0004/°C for CMOS. The frequency shift between idle and active gives ΔT at each sensor position.

The thermal model is steady-state 2D heat conduction on a thin silicon slab:

```
ΔT(sensor) = Σ_zones [ N_luts × P_lut × G(r) ]
G(r) = ln(R_die/r) / (2π κ t)
```

where κ = 148 W/(m·K), t = 300 μm, R_die = 5 mm. Multiple sensors at different distances from each zone give an overdetermined system. Least-squares regression extracts P_lut.

DTR cross-validates: `ΔT_DTR / Θ_JA = P_total`, where Θ_JA = 20°C/W (CABGA256 datasheet).

WolframScript computes correction factors against Lattice published cell power data and scales all cell types proportionally.

## Hardware

- Board: IcePi Zero (Lattice ECP5U-25F, CABGA256)
- Clock: 50 MHz oscillator, divided to 25 MHz system clock
- 192 ring oscillator stages (8 sensors × 5 stages + 4 zones × 500 LUTs)
- DTR primitive for absolute temperature

## Resource Usage

- LUT4: ~2,040 (work LUTs) + 40 (sensor rings) + controller
- DP16KD: 0
- Fmax: not timing-critical (ring oscillators are asynchronous)

## Reproducing

```
python icepi_helper.py build power-calibration --clean
python icepi_helper.py install power-calibration --slot boot --reload
# Wait ~4 minutes for full 8-phase sweep (8 × 30s)
# Capture UART output to file
python experiments/power-calibration/parse_results.py results_raw.bin
```

## Files

| File | Role |
|------|------|
| `top.sv` | Calibration device: zones, sensors, sweep controller, UART output |
| `power_calibration_placement.lpf` | Die position constraints for sensors and zones |
| `build.json` | nextpnr flags: --ignore-loops --timing-allow-fail |
| `parse_results.py` | UART parser, thermal model solver, WolframScript integration |
| `README.md` | This file |
