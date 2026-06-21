# The module contract

Every composable module in `modules/` obeys one interface. Once you know it, the
~85 modules become **one pattern plus ~85 data points**: read this document and
the canonical exemplar (`modules/anvil/anvil.sv`), and any other module's `.sv`
is skimmable in seconds. Per-module register maps are already machine-readable —
`python icepi_helper.py digest <name>` or the `registers` field in each
`module.json` — so you rarely need to open the source at all.

## The register bus (every module has exactly these ports)

```systemverilog
module <name> (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,    // byte address within this module's 4 KB region
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,      // write strobe, one cycle
    input  wire        reg_rd,      // read strobe, one cycle
    output logic [31:0] reg_rdata,
    output logic        reg_ready   // transaction complete, one cycle
);
```

The compositor gives each module a 4 KB register window and decodes
`mem_addr[31:24]` to one of sixteen address nibbles (`0x30`–`0x3F`). Inside the
module, registers are word-addressed: decode on `reg_addr[N:2]` (the low two bits
are the byte-in-word and are ignored). Most modules use `reg_addr[4:2]` (8 word
slots); wider maps use `[5:2]`, `[6:2]`, or compare `reg_addr[11:8]` for banked
regions (tables, buffers).

## The handshake

```systemverilog
always_ff @(posedge clk) begin
    reg_ready <= 1'b0;                 // default: not ready
    if (rst) begin
        // reset all state
    end else begin
        if (reg_wr) begin
            reg_ready <= 1'b1;          // ack the write this cycle
            case (reg_addr[4:2]) ... endcase
        end
        if (reg_rd) begin
            reg_ready <= 1'b1;          // ack the read; drive reg_rdata
            case (reg_addr[4:2]) ... endcase
        end
    end
end
```

Rules: `reg_ready` pulses for exactly one cycle when a transaction completes;
combinational results may be precomputed in `wire`s and merely selected in the
`reg_rd` arm; a write strobe and the value it commits are both valid on the same
cycle. The compositor's per-module strobe fires only when the address matches, a
bus request is live, the bus has not already acked this cycle, and the module has
not already raised `reg_ready` — which is why a module must drop `reg_ready` back
to 0 by default each cycle.

## Optional interfaces (declared in `module.json` `interfaces.requires`)

- **`snoop`** — passive bus tap for observers (SCRY, ECHO, HEAT, TRAP, GAUGE,
  DEPTH). Adds `snoop_addr[31:0]`, `snoop_wstrb[3:0]`, `snoop_valid`,
  `snoop_ready`. A snooping module **must** declare `snoop_wstrb` (the compositor
  wires `mem_wstrb` to it unconditionally; a missing port fails synthesis — this
  is a tested invariant).
- **`irq`** — `irq_out`, active-OR'd into the CPU's external interrupt line.
- **`dma`** — an active bus-master port (`dma_addr/dma_rd/dma_rdata/dma_ready`),
  used by IRIS. When any module requires `dma`, the compositor generates a
  priority bus arbiter (CPU wins ties; the master reads in the gaps).

## Recurring idioms

- **Done-latch discipline.** Engines that drive a sub-block with a `start` pulse
  and wait for `done` latch the completion with start-clears-first priority:
  ```systemverilog
  if (start)      done_latch <= 1'b0;   // start always beats a stale done
  else if (done)  done_latch <= 1'b1;
  ```
  This prevents a `done=1` left over from the previous operation from
  re-triggering on the same cycle as a new `start`. Used in the flash/SD/SDRAM
  engines, the install engine, and auto-recovery.

- **Ring-oscillator entropy (`(* keep *)`).** TRNG modules (EMBER, EMBER-LITE,
  MARK) build free-running ring oscillators from `LUT4` primitives configured as
  inverters, with `(* keep *)` on the chain so synthesis does not optimize the
  combinational loop away:
  ```systemverilog
  (* keep *) wire [RING_STAGES:0] r;
  assign r[0] = r[RING_STAGES];
  (* keep *) LUT4 #(.INIT(16'h5555)) inv (.Z(r[st+1]), .A(r[st]), ...);
  ```

- **`$readmemh` / `initial`-block ROMs.** Lookup tables (sine quarter-waves, the
  AES S-box, the RUNE font) are pure-function `case` ROMs or `initial`-loaded
  arrays, which survive ECP5 synthesis predictably.

## The canonical exemplar: ANVIL

`modules/anvil/anvil.sv` is the reference. It is a hardware CRC-32 accelerator —
the smallest module that exercises the full contract (registered state, a
combinational `wire` result selected on read, a control register, counters):

```
0x000 W DATA     feed one byte; CRC updates immediately
0x004 R CRC      current CRC-32 (finalized / inverted)
0x008 W CONTROL  bit 0 = reset CRC to 0xFFFFFFFF
0x00C R RAW      raw (non-inverted) CRC state
0x010 R COUNT    bytes fed since reset
```

Read its ~80 lines once; every other module is a variation on it.

## Manifest and tests

Each module ships:

- `module.json` — name, description, `resources` (luts/brams/multipliers, kept
  honest by `scripts/verify_manifest_luts.py`), `interfaces`, `top_module`, and
  the `registers` map (lifted from the `.sv` header by
  `scripts/extract_registers.py`, checked in CI with `--check`).
- `test_<name>.py` — a silicon compositor test (RIME-I + the module, verified
  against a Python predictor via `compositor_test.run_module_test`).
- `test_<name>_torture.py` — a hash-chain torture test built with
  `torture_gen.TortureBuilder`, swept offline by `modules/torture_sweep.py`.

To add a module: write `<name>.sv` to the contract, document its register map in
the header comment, `module.json` it (run `extract_registers.py --write` and
`verify_manifest_luts.py --update`), and add the two test files. The compositor
(`icepi/compose.py`) wires it automatically by scanning instantiation patterns.
