# Flipper Stimulus

Controlled RF stimulus experiment using the RF sensor grid.

## What it does

Uses the Flipper Zero at 433.92 MHz as a controlled RF source to map electromagnetic coupling patterns on the ECP5-25F die. The FPGA runs the RF sensor grid experiment while the host script orchestrates baseline/stimulus/post-stimulus captures and computes differential frequency maps.

## Prerequisites

- RF sensor bitstream loaded on IcePi Zero (COM9)
- Flipper Zero connected via USB (~2 inches from FPGA)

## Usage

```bash
# Flipper at 433.92 MHz (default)
python run_stimulus.py --baseline 5 --stimulus 10 --post 5

# Flipper at different frequency
python run_stimulus.py --source flipper --freq 315000000

# Analyze results
python parse_differential.py results_flipper.txt
```

## What to expect

Ring oscillator frequencies shift when external RF fields modulate local supply voltage through bond wire and routing layer coupling. The spatial pattern of shifts reveals:
- Which die regions couple most strongly to external RF
- Whether the coupling is dominated by bond wire geometry or internal routing
- Distance dependence (move Flipper closer/farther and compare)

Measured: mean shift -0.6%, max -7.93% at ring 102 (row 6, col 6) with Flipper at 2 inches transmitting 433.92 MHz OOK.
