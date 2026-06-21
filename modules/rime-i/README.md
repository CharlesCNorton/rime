# RIME-I

Minimal RV32I base integer CPU. The simplest RIME processor: 37 instructions, no multiply/divide, no pipeline. Runs C compiled with `-march=rv32i -mabi=ilp32`. Software multiply/divide from libgcc.

RIME-I is the first module in the RIME compositor system. It exists so the IcePi Zero can execute programs autonomously without a host connection.

## ISA

RV32I base integer instruction set (RISC-V Volume 1, Chapter 2):

- **Integer computation**: ADD, SUB, AND, OR, XOR, SLT, SLTU, SLL, SRL, SRA (register and immediate forms)
- **Loads/stores**: LB, LH, LW, LBU, LHU, SB, SH, SW
- **Branches**: BEQ, BNE, BLT, BGE, BLTU, BGEU
- **Jumps**: JAL, JALR
- **Upper immediate**: LUI, AUIPC
- **System**: ECALL, EBREAK

No M extension (multiply/divide). No C extension (compressed). No F/D (floating point). No A (atomic). GCC handles multiply and divide in software.

## Architecture

- Single-issue, multi-cycle (no pipeline)
- 32 x 32-bit general-purpose registers (x0 hardwired to 0)
- 32-bit program counter
- Unified instruction/data memory in BRAM (4 KB default)
- Memory-mapped I/O for UART and service bridge
- 25 MHz clock (shared with RIME service)

## Memory Map

| Address | Size | Description |
|---------|------|-------------|
| 0x00000000 | 4 KB | BRAM: instruction and data memory |
| 0x20000000 | 4 B | UART TX data (write) |
| 0x20000004 | 4 B | UART TX busy (read) |
| 0x20000008 | 4 B | UART RX data (read) |
| 0x2000000C | 4 B | UART RX valid (read, clears on read) |

## Resource Budget

| Resource | Estimate | Available | Utilization |
|----------|----------|-----------|-------------|
| LUT4 | ~1,500 | 20,885 | ~7% of remaining |
| DP16KD | 2 | 56 | 4% |
| MULT18X18D | 0 | 28 | 0% |

## Files

| File | Role |
|------|------|
| `module.json` | Module manifest |
| `rime_i_core.sv` | RV32I core: decoder, ALU, register file, PC |
| `rime_i_top.sv` | Module top: BRAM, memory map, UART bridge |
| `fw/Makefile` | Cross-compilation build |
| `fw/start.S` | Startup: set stack pointer, call main, halt |
| `fw/link.ld` | Linker script: text/data/bss/stack layout |
| `tests/` | Simulation testbenches |

## Building Firmware

```
cd modules/rime-i/fw
make
```

Requires `riscv32-unknown-elf-gcc` in PATH.

## Composing

```
python icepi_helper.py compose rime-i --slot boot --build --reload
```
