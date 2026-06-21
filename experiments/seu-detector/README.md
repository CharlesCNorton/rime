# SEU Detector

Passive particle and electromagnetic upset monitor for the ECP5-25F.

## What it does

Fills the FPGA with 4096 flip-flops holding known patterns, then continuously scans them for spontaneous bit flips. Any mismatch is a Single Event Upset (SEU) — a bit that changed due to a charged particle or external electromagnetic interference.

## Architecture

- 128 groups × 32-bit registers = 4096 FFs
- Each group holds a unique pattern: `0xA5A5A5A5 ^ {4{index}}`
- Sequential scan: 2 clocks per group, 256 clocks per full scan
- At 12.5 MHz: ~48,828 full scans/second, ~200M bit-checks/second
- Per-group 1-second cooldown suppresses re-reporting from stuck bits
- Reference ring oscillator tracks temperature via frequency

## Expected results

At sea level, the cosmic ray SEU rate for 4096 FFs is roughly one event per 30+ years. Zero detections is the expected baseline. The experiment becomes interesting with a controlled RF source (Flipper Zero, LoRa) or in high-radiation environments.

## Output format

```
SEU DETECTOR ECP5
C,0080,0020,A5A5A5A5
S,<scans>,<flips>,<uptime>,<ring_freq>
F,<group>,<xor_mask>,<scan_count>
```

## Build and run

```
python icepi_helper.py install seu-detector --slot boot --reload --build
```

Capture output with any serial terminal at 115200 baud on COM9.
