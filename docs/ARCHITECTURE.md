# RIME Architecture

## Layer Diagram

```
┌──────────────────────────────────────────────────────────┐
│  Host CLI (icepi_helper.py, icepi_admin.py)              │
│    40+ subcommands: build, install, compose, doctor, ... │
├──────────────────────────────────────────────────────────┤
│  icepi/ Python library                                    │
│    flash_service.py  — UART transport + protocol client   │
│    compose.py        — N-way compositor + top.sv codegen  │
│    build.py          — nosis → nextpnr → ecppack pipeline │
│    bundle.py         — SD/raw-media bundle format         │
│    sd.py             — SD partitions, FAT32, auto-recovery│
│    layout.py         — flash slot map + aliases           │
│    protocol.py       — command/error/state name tables    │
├──────────────────────────────────────────────────────────┤
│  UART (115200 8N1, length-prefixed framing)               │
├──────────────────────────────────────────────────────────┤
│  RIME firmware (top.sv + rime_service.sv)                 │
│    Clock divider → startup sequencer → UART RX/TX         │
│    rime_service FSM (17 states, 27 commands)              │
│    CRC-8 frame inject chain                               │
│    Watchdog timer                                         │
│    CRC-32 range helper FSM                                │
├────────────────┬─────────────────┬───────────────────────┤
│ Flash SPI      │ SDRAM           │ SD SPI                 │
│ flash_spi_     │ sdram_          │ sd_spi_                │
│ master.sv      │ controller.sv   │ master.sv              │
│ W25Q128 QSPI   │ + sdram_        │ SDHC/SDSC              │
│ 16 MB           │   bridge.sv     │ SPI mode               │
│                │ W9825G6KH 32 MB │                        │
├────────────────┴─────────────────┴───────────────────────┤
│  sd_install_engine.sv  — firmware-mediated bundle install  │
│  auto_recovery.sv      — boot-time SD-to-flash restore    │
└──────────────────────────────────────────────────────────┘

Compositor path (JTAG, not UART):

┌──────────────────────────────────────────────────────────┐
│  compose.py — validate resources, assign addresses,       │
│               generate top.sv wrapper                     │
├──────────────────────────────────────────────────────────┤
│  RIME-I (rime_i_core.sv)   — RV32I soft CPU, 5-state FSM │
│  BRAM (14 KB, 7 DP16KD)   — firmware via $readmemh       │
│  UART TX/RX               — CPU ↔ host communication     │
│  Module bus (0x30-0x3F)   — up to 16 hardware modules     │
│    Standard: reg_addr, reg_wdata, reg_wr/rd, reg_rdata    │
│    Optional: snoop (bus tap), irq (active-OR)             │
├──────────────────────────────────────────────────────────┤
│  Module library (75 modules, each with module.json)       │
└──────────────────────────────────────────────────────────┘
```

## Data Paths

### Flash Update (staged)

```
Host → SDRAM_WRITE_STREAM → SDRAM (full bitstream)
     → SDRAM_TO_FLASH     → Flash SPI (erase + program at SPI speed)
     → SDRAM_VERIFY_FLASH  → compare SDRAM vs flash on-board
```

### Flash Update (SD bundle install)

```
Host → SD_WRITE512    → SD card (bundle header + payload)
     → SD_INSTALL     → sd_install_engine reads SD, writes flash
                         (header parse → sector erase → 16-byte program loop)
```

### Auto-Recovery (boot-time)

```
Power-on → auto_recovery.sv
         → SD_INIT → read control block at LBA 1
         → validate magic + version + checksum + armed flag
         → sd_install_engine → flash
         → any UART byte aborts (operator never locked out)
```

## FSM States (rime_service.sv)

| State | Name | Purpose |
|-------|------|---------|
| 0 | IDLE | Wait for UART byte |
| 1 | DISPATCH | Decode command, gate by app_mode |
| 2 | TX_RESP | Drain response FIFO |
| 3 | RX_BYTES | Collect multi-byte payload |
| 4 | WAIT_SPI | Poll flash SPI completion |
| 5 | WAIT_SDRAM | Poll SDRAM bridge |
| 6 | SDRAM_FLASH_LOOP | On-board erase/program loop |
| 7 | SDRAM_STREAM | Bulk UART → SDRAM transfer |
| 8 | SDRAM_VERIFY | On-board SDRAM vs flash compare |
| 9-11 | RAW_* | Single-word SDRAM access |
| 12 | WAIT_SD | Poll SD SPI master |
| 13 | SD_WRITE_RX | Receive 512 bytes for SD_WRITE512 |
| 14-15 | RAW_READ_* | Multi-word raw read pipeline |
| 16 | WAIT_INSTALL | Wait for sd_install_engine |

## Bus Muxing (top.sv)

Three drivers share the SD SPI master:
1. `rime_service` — normal commands (SD_READ16, SD_WRITE512, etc.)
2. `cr_active` — SD_CRC32_RANGE helper FSM
3. `inst_active` — sd_install_engine (host-driven or auto-recovery)

Install has highest priority; CRC-range is second; service is default.

The flash SPI master is shared between `rime_service` and `inst_active` with the same priority scheme.

## Module Bus Protocol

Each compositor module sees:
- `reg_addr[11:0]` — 4 KB address space per module
- `reg_wdata[31:0]` — write data from CPU
- `reg_wr` — write strobe (active one cycle)
- `reg_rd` — read strobe (active one cycle)
- `reg_rdata[31:0]` — read data to CPU
- `reg_ready` — transaction complete (active one cycle)

Snoop modules additionally see:
- `snoop_addr[31:0]` — full CPU bus address
- `snoop_wstrb[3:0]` — byte strobes
- `snoop_valid` — bus transaction active
- `snoop_ready` — bus transaction completing

## Test Suites

| Suite | Target | Runner | Coverage |
|-------|--------|--------|----------|
| Offline Python | icepi/ library | `pytest tests/` | MockSerial + Hypothesis |
| Board regression | RIME firmware on silicon | `tests/regression.py` | CRC-32 chain through every subsystem |
| Composition regressions | RIME-I + modules on silicon | `modules/compositions/*.py` | Python predictor vs UART readback |
| Module torture | All 75 modules (offline) | `modules/torture_sweep.py` | Hash-chain through register read/write |
| HDL compilation | Testbenches | `iverilog` in CI | Syntax + elaboration |
| Simulation | SDRAM controller | `tb_sdram_roundtrip.sv` | Write/read/row-switch |
