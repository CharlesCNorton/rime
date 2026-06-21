# AGENTS.md — front door for automated contributors

RIME (Resident IcePi Management Environment) is a control plane for the IcePi
Zero (Lattice ECP5U-25F): a resident UART boot image plus a host-side Python CLI
that build, install, verify, and recover FPGA bitstreams, and a compositor that
fuses an RV32I soft CPU with a library of hardware modules into one image.

The repository looks enormous but is not. It is a small set of patterns stamped
out many times: ~85 hardware modules share **one** register-bus contract, each
module is a manifest plus boilerplate tests around a register map, and the seven
themed compositions and three coprocessors are one shape each. **Do not read the
whole tree.** Read the map, then lazy-load instances on demand.

## First move: the digest

```
python icepi_helper.py digest          # human summary of the whole repo
python icepi_helper.py digest --json   # machine-readable index (~30K tokens)
python icepi_helper.py digest anvil    # one module's register map
```

`digest --json` aggregates everything single-sourced — the protocol tables, the
flash/SDRAM memory map, the compositor budget, and the module registry (incl.
every module's register map). It is the index to the entire repository; reach for
it before `find` + read.

## Ordered ingestion path (~10 files = whole system)

Read these, in order, and you understand RIME end to end:

1. `AGENTS.md` (this file) and `README.md` — what it is, the workflows.
2. `docs/ARCHITECTURE.md` — layer diagram, data paths, FSM state table, bus mux.
3. `PROTOCOL.md` — the UART command set and framing.
4. `docs/MODULE_CONTRACT.md` — the one contract all modules obey; read with
   `modules/anvil/anvil.sv`, the canonical exemplar.
5. `icepi/protocol.py` — command bytes, error codes, capability flags, CRC-8
   (single source of truth for the wire protocol).
6. `icepi/flash_service.py` — the host UART transport client and every command.
7. `firmware/images/rime/rime_service.sv` — the resident service FSM
   (state bodies are split into the `rime_svc_*.svh` includes).
8. `firmware/images/rime/top.sv` — clock/reset, engine instantiation, and the
   4-way bus mux (install → recovery → CRC-range → service).
9. `icepi/compose.py` — the N-way compositor and resource budgeting.
10. `modules/<name>/<name>.sv` on demand — any one is skimmable once you know the
    contract; its register map is already in `digest --json` and `module.json`.

Everything else (the other ~84 modules, their manifests and tests, the themed
compositions, the testbenches) is an instance of a pattern above. Pull it only
when you touch it.

## Commands

```
python icepi_helper.py digest                 # repo index (no board)
python icepi_helper.py build --list           # known firmware projects
python icepi_helper.py build rime --clean     # nosis -> nextpnr -> ecppack
python icepi_helper.py compose anvil cairn scry --validate-only   # budget check
python icepi_helper.py status                 # probe the board over UART
python icepi_helper.py doctor                 # full board health report
python icepi_helper.py board-test             # exercise the live path (non-destructive)
python modules/torture_sweep.py               # offline: all module test firmwares + BRAM fit

python -m pytest tests/ -q                    # offline host suite (needs pytest+hypothesis)
python scripts/extract_registers.py --check   # module.json registers vs .sv source (CI)
python scripts/verify_manifest_luts.py        # module.json LUT counts vs fresh synth (CI)
python scripts/silicon_drift.py               # board fingerprint + chain regression (needs board)
```

Synthesis is [nosis](https://github.com/CharlesCNorton/nosis) (`pip install
nosis`), invoked as `python -m nosis` in the same Python. The back-end toolchain
(`nextpnr-ecp5`, `ecppack`, `ecpbram`, `openFPGALoader`, `iverilog`) is
auto-discovered from an `oss-cad-suite/` near the repo or on PATH —
no env vars required. Override with `ICEPI_OSS_CAD_ROOT` if needed.

## Invariants (enforced by tests/test_build.py — keep them true)

- Host and firmware agree on magic: `AUTO_MAGIC`, `AUTO_CONTROL_LBA`
  (icepi/models.py ↔ firmware/core/auto_recovery.sv) and `BUNDLE_MAGIC`
  (icepi/models.py ↔ sd_install_engine.sv).
- No module declares `luts == 0 && multipliers == 0` (an unmeasured budget).
- Every module that uses the `snoop` interface declares a `snoop_wstrb` port.
- Only `icepi/flash_service.py` may call `FlashService._exchange`; everyone else
  uses the public `raw_exchange`.
- `build` subprocess calls reference only flags the parser accepts.
- `module.json` register maps stay in sync with the `.sv` source
  (`scripts/extract_registers.py --check`).

## Gotchas

- **`(* keep *)` protects silicon behavior.** Several signals in `top.sv` and
  `rime_service.sv` carry `(* keep *)` to stop the synthesizer constant-folding
  signals in combinational/feedback paths (app_mode, the CRC-8 inject chain,
  the startup sequencer). Removing them breaks ENTER_SERVICE on silicon.
- **`experiments/` is out of scope.** Standalone whole-FPGA images; ignore unless
  asked. They still appear in `build --list`.
- **Linux serial access** needs the user in the `dialout` group
  (`sudo usermod -aG dialout $USER`, then re-login); the port is `root:dialout`.
- **One file per concern.** Each module is a single `.sv`; the service FSM splits
  state bodies into `.svh` includes; don't scatter a module across files.
- **House style:** proof terms of intent in comments end in periods; register
  maps live in the `.sv` header comment (and are lifted into `module.json` by
  `scripts/extract_registers.py`); keep both in sync.

## Repository map

```
icepi/                 host package (protocol, transport, compose, build, sd, layout, models, tools)
icepi/commands/        CLI verb implementations (digest, info, flash, sd, install, shell, ...)
icepi_helper.py        CLI entry point        icepi_admin.py   driver/JTAG admin wrapper
firmware/core/         shared engines (uart, flash_spi, sdram, sd_spi, install, auto_recovery)
firmware/images/       rime, ember            (each: top.sv + image-specific sources)
modules/               ~85 composable modules (each: <name>.sv, module.json, tests) + rime-i CPU
modules/compositions/  seven themed silicon regressions + the compositor verifier
tests/                 offline pytest (MockSerial + Hypothesis) + board regression.py
scripts/               drift/manifest/bench/extract tooling
docs/                  ARCHITECTURE, THROUGHPUT, MODULE_CONTRACT
config/                icepi-layout.json (flash slots + SDRAM windows), board config
```
