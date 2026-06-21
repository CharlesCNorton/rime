# Experiment Template

Copy this directory, rename it, edit `experiment.c`.

## How it works

The experiment compiles to a standalone RISC-V binary that runs on the PicoRV32 CPU. The RIME boot ROM loads it from flash at `0x300000` on reset. No FPGA rebuild needed — the experiment uses the existing CPU image's hardware (UART, GPIO, timer, watchdog, CRC32 coprocessor).

## Running

```
cd firmware/tests/experiments/my_experiment
make
python icepi_helper.py fw-upload firmware/my_experiment/experiment.bin --reset
```

Results appear over UART at 115200 baud. The `--reset` flag triggers a software reset; the boot ROM loads the new binary and the experiment runs immediately.

## Restoring RIME

The experiment erases its own RMFW header from flash after printing results. To reboot into the RIME service, send `R` over UART:

```python
import serial
s = serial.Serial("COM9", 115200)
s.write(b"R")
s.close()
```

The board resets, the boot ROM finds no firmware in flash, and the default RIME service starts. No JTAG reload, no manual erase, no touching the board.

To run another experiment immediately, just `fw-upload` the next one with `--reset`.

## Available hardware

| Address | Peripheral | Notes |
|---------|------------|-------|
| `0x20000000` | UART TX | Write byte to 16-entry TX FIFO |
| `0x20000004` | UART RX | Read: `{valid[31], byte[7:0]}` |
| `0x20000008` | UART status | Bit 0: TX FIFO not full, Bit 1: RX available |
| `0x50000000` | Timer compare | Read/write |
| `0x50000004` | Timer counter | Read-only, free-running at 25 MHz |
| `0x60000000` | GPIO LED | 5-bit LED output |
| `0x60000004` | GPIO button | 2-bit button input |
| `0x70000008` | Watchdog config | Write timeout (0=disable), read current |
| `0x7000000C` | Watchdog pet | Write any value to reset counter |

The CRC32 coprocessor is available via inline asm:

```c
unsigned int result;
asm volatile (".insn r 0x2B, 0, 0, %0, %1, %2"
              : "=r"(result) : "r"(crc), "r"(byte));
```

SPI flash, SD card, and SDRAM are NOT available — the experiment firmware replaces the RIME service that drives those peripherals. If your experiment needs flash/SD/SDRAM access, implement the MMIO protocol directly (see `rime_fw.c` for register definitions).

## Constraints

- Maximum binary size: 16,384 bytes (16 KB BRAM)
- Stack grows down from `0x4000`
- Watchdog: 60 seconds. Call `WDOG_PET = 1` in any loop that runs longer.
- UART: 115200 baud, 8N1. TX is FIFO-buffered (16 bytes). Check `UART_STATUS & 1` before writing.
- The boot ROM occupies `0xF0000000`. Don't write to that address range.
