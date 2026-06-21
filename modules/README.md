# RIME Modules

Modules are composable FPGA building blocks. Each module is a self-contained HDL design with a defined interface, resource budget, and optional firmware. The compositor combines a selection of modules into a single bitstream.

## Architecture

The RIME service (flash, SD, SDRAM, UART protocol) is always present. Modules are instantiated alongside the service in the remaining FPGA resources. The app shell routes commands: ENTER_SERVICE for the resident service, module-specific commands for active modules.

## Resource Budget (ECP5U-25F)

| Resource | Total | RIME Service | Available |
|----------|-------|-------------|-----------|
| LUT4 | 24,288 | 3,403 (14%) | 20,885 (86%) |
| DFF | 24,288 | 2,646 (10%) | 21,642 (90%) |
| DP16KD (BRAM) | 56 | 0 | 56 |
| MULT18X18D | 28 | 0 | 28 |

## Module Manifest

Each module directory contains a `module.json`:

```json
{
  "name": "rime-i",
  "version": "0.1.0",
  "description": "RV32I base integer CPU",
  "resources": {
    "luts": 1500,
    "brams": 2,
    "multipliers": 0
  },
  "interfaces": {
    "requires": ["uart_tx", "uart_rx", "clock", "reset"],
    "provides": ["cpu_bus"]
  },
  "firmware": "fw/",
  "top_module": "rime_i_top"
}
```

## Module Categories

- **CPU**: Soft processors (RIME-I)
- **Memory**: SLAB (Stackable LUT Allocated Block) tiles
- **Peripheral**: Hardware accelerators, I/O controllers, sensors
- **Experiment**: Ring oscillators, entropy sources (EMBER), measurement circuits

Experiments under `experiments/` are standalone images that take the whole FPGA. Modules under `modules/` are designed for composition.

## Directory Structure

```
modules/
  README.md               This file
  <module-name>/
    module.json            Manifest: resources, interfaces, metadata
    README.md              Module documentation
    *.sv                   HDL source files
    fw/                    Optional firmware (C, assembly, linker scripts)
    tests/                 Module-specific tests
```

## Compositor

The compositor (`icepi/compose.py`) reads module manifests, validates the combined resource budget fits the ECP5U-25F with 10% margin, assigns each module a unique address region (0x30-0x3F), generates a top-level wrapper with RIME-I + N modules, and builds through the standard nosis/nextpnr/ecppack pipeline.

```
# Validate without building
python icepi_helper.py compose anvil cairn scry --validate-only

# Compose and build
python icepi_helper.py compose anvil cairn scry --clean

# Up to 16 modules
python icepi_helper.py compose anvil cairn scry sift flux epoch
```

Address map: module 0 at `0x30xxxxxx`, module 1 at `0x31xxxxxx`, etc. Each module gets a 16 MB address region with 12-bit register addressing.

## Bus Interface

Standard (all modules):
- `reg_addr[11:0]` — byte address within module region
- `reg_wdata[31:0]` — write data
- `reg_wr` — write strobe (one cycle)
- `reg_rd` — read strobe (one cycle)
- `reg_rdata[31:0]` — read data
- `reg_ready` — transaction complete

Optional (declared in module.json `interfaces.requires`):
- `snoop` — adds `snoop_addr[31:0]`, `snoop_valid`, `snoop_ready` for passive bus observation (used by SCRY)
