# RF Sensor Grid

Spatial electromagnetic field sensor using a placed ring oscillator grid on the ECP5-25F.

## What it does

256 ring oscillators arranged in a 16x16 grid across all 4 logic blocks of the die. Each ring's frequency shifts in response to local electromagnetic fields. The spatial frequency map is a 2D image of the RF environment at the die surface.

External RF sources (Flipper Zero at 433 MHz, LoRa at 915 MHz, ambient EMI) induce currents in bond wires and metal routing layers, modulating local supply voltage and shifting ring frequencies. The differential measurement between baseline and stimulus sweeps reveals the spatial coupling pattern.

## Architecture

- 256 rings, 5-stage LUT4 inverter chains (~250 MHz nominal)
- LPF LOCATE constraints fix each ring to a known tile on the die
- 16x16 grid spanning all 4 logic blocks (rows 3-44, columns 2-62)
- 1ms measurement windows (12,500 cycles at 12.5 MHz)
- Full sweep: ~256ms (256 rings × ~1ms each)
- Continuous sweeps with UART output between each

## Grid layout

```
Block 4 (rows 38-44): ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●  (rows 38,40,42,44)
                       ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●
═══ BRAM stripe (row 37) ═══════════════════════════════════
Block 3 (rows 26-36): ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●  (rows 27,30,33,36)
                       ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●
═══ BRAM stripe (row 25) ═══════════════════════════════════
Block 2 (rows 14-24): ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●  (rows 15,18,21,24)
                       ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●
═══ DSP stripe (row 13) ════════════════════════════════════
Block 1 (rows 2-12):  ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●  (rows 3,6,9,12)
                       ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●
```

## Output format

```
RF SENSOR ECP5
G,10,10,01,0100
R,<sweep>,<ring_idx>,<edge_count>
T,<sweep>,<ring_freq>
```

## Build and run

```
python icepi_helper.py install rf-sensor --slot boot --reload --build
```

For Flipper Zero stimulus experiments, see `experiments/flipper-stimulus/`.
