"""N-way compositor: generate a top.sv for RIME-I + N modules.

Reads module.json manifests, validates the combined resource budget
fits the ECP5U-25F, generates address decoding for up to 16 modules
(address region 0x30-0x3F), and builds through the standard pipeline.

Bus interface per module:
  Standard (all modules):
    reg_addr[11:0], reg_wdata[31:0], reg_wr, reg_rd, reg_rdata[31:0], reg_ready

  Optional (declared in module.json "interfaces.requires"):
    snoop:  snoop_addr[31:0], snoop_valid, snoop_ready — passive bus tap
    irq:    irq_out — active-high interrupt line (active-OR'd into CPU)

Usage:
    from icepi.compose import compose, validate_composition
    plan = validate_composition(["anvil", "cairn", "scry"])
    top_sv = compose(plan, firmware_words)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from icepi.tools import REPO_ROOT

__all__ = [
    "DEVICE_LUTS",
    "DEVICE_BRAMS",
    "DEVICE_MULTS",
    "RIME_I_LUTS",
    "RIME_I_BRAMS",
    "CompositionError",
    "ModuleSpec",
    "CompositionPlan",
    "load_module_spec",
    "validate_composition",
    "compose",
    "generate_and_build",
]

MODULES_ROOT = REPO_ROOT / "modules"

DEVICE_LUTS = 24288
DEVICE_BRAMS = 56
DEVICE_MULTS = 28

RIME_I_LUTS = 4050
RIME_I_BRAMS = 7
PLATFORM_OVERHEAD_LUTS = 800
MARGIN_PERCENT = 10


class CompositionError(RuntimeError):
    pass


@dataclass(slots=True)
class ModuleSpec:
    name: str
    luts: int
    brams: int
    mults: int
    top_module: str
    sources: list[str]
    requires_snoop: bool = False
    requires_irq: bool = False
    requires_dma: bool = False
    description: str = ""

    @property
    def sv_files(self) -> list[Path]:
        mod_dir = MODULES_ROOT / self.name
        return [mod_dir / s for s in self.sources]


@dataclass(slots=True)
class CompositionPlan:
    modules: list[ModuleSpec]
    total_luts: int
    total_brams: int
    total_mults: int
    available_luts: int
    available_brams: int
    available_mults: int
    fits: bool
    address_map: dict[str, int]


def load_module_spec(name: str) -> ModuleSpec:
    mod_dir = MODULES_ROOT / name
    mj = mod_dir / "module.json"
    if not mj.exists():
        raise CompositionError(f"module `{name}` has no module.json")
    data = json.loads(mj.read_text(encoding="utf-8"))
    resources = data.get("resources", {})
    interfaces = data.get("interfaces", {})
    requires = [r.lower() for r in interfaces.get("requires", [])]

    sv_files = [f.name for f in sorted(mod_dir.glob("*.sv")) if f.name != "top.sv"]
    if not sv_files:
        raise CompositionError(f"module `{name}` has no .sv source files")

    return ModuleSpec(
        name=name,
        luts=resources.get("luts", 0),
        brams=resources.get("brams", 0),
        mults=resources.get("multipliers", 0),
        top_module=data.get("top_module", name),
        sources=sv_files,
        requires_snoop="snoop" in requires or "bus_snoop" in requires,
        requires_irq="irq" in requires,
        requires_dma="dma" in requires,
        description=data.get("description", ""),
    )


def validate_composition(module_names: list[str]) -> CompositionPlan:
    if not module_names:
        raise CompositionError("at least one module is required")
    if len(module_names) > 16:
        raise CompositionError("maximum 16 modules (address nibbles 0x30-0x3F)")

    # rime-i is the implicit CPU and is accounted for via RIME_I_LUTS and
    # RIME_I_BRAMS below. Listing it as a module would double-count its
    # resources and produce duplicate top-level instantiation in compose().
    if "rime-i" in module_names:
        raise CompositionError(
            "rime-i is the implicit CPU and cannot be listed as a module; "
            "remove it from the module list (its resources are added automatically)"
        )

    seen: set[str] = set()
    modules: list[ModuleSpec] = []
    for name in module_names:
        if name in seen:
            raise CompositionError(f"duplicate module: {name}")
        seen.add(name)
        modules.append(load_module_spec(name))

    mod_luts = sum(m.luts for m in modules)
    mod_brams = sum(m.brams for m in modules)
    mod_mults = sum(m.mults for m in modules)

    total_luts = RIME_I_LUTS + PLATFORM_OVERHEAD_LUTS + mod_luts
    total_brams = RIME_I_BRAMS + mod_brams
    total_mults = mod_mults

    margin = DEVICE_LUTS * MARGIN_PERCENT // 100
    avail_luts = DEVICE_LUTS - margin
    avail_brams = DEVICE_BRAMS
    avail_mults = DEVICE_MULTS

    fits = (total_luts <= avail_luts and
            total_brams <= avail_brams and
            total_mults <= avail_mults)

    address_map = {}
    for i, m in enumerate(modules):
        address_map[m.name] = 0x30 + i

    if not fits:
        over = []
        if total_luts > avail_luts:
            over.append(f"LUTs {total_luts}/{avail_luts}")
        if total_brams > avail_brams:
            over.append(f"BRAMs {total_brams}/{avail_brams}")
        if total_mults > avail_mults:
            over.append(f"DSPs {total_mults}/{avail_mults}")
        raise CompositionError(
            f"composition exceeds budget: {', '.join(over)}. "
            f"Modules: {[m.name for m in modules]}"
        )

    return CompositionPlan(
        modules=modules,
        total_luts=total_luts,
        total_brams=total_brams,
        total_mults=total_mults,
        available_luts=avail_luts,
        available_brams=avail_brams,
        available_mults=avail_mults,
        fits=fits,
        address_map=address_map,
    )


def compose(plan: CompositionPlan, firmware: list[int], *, mem_words: int = 1024) -> str:
    """Generate a complete top.sv for the given composition plan and firmware.

    The generated module contains: clock divider, reset sequencer, RIME-I
    CPU, BRAM with firmware initialization, UART TX/RX, and one instantiation
    per module with address decode on mem_addr[31:24]. Flash, SD, and SDRAM
    pins are tied to safe defaults (the compositor path uses JTAG, not UART).
    """
    lines: list[str] = []
    a = lines.append

    a("module top (")
    a("    input  wire        clk,")
    a("    input  wire        usb_rx,")
    a("    output wire        usb_tx,")
    a("    output logic [4:0] led,")
    a("    input  wire [1:0]  button,")
    a("    output wire        flash_csn, output wire flash_mosi,")
    a("    output wire        flash_wpn, output wire flash_resetn,")
    a("    input  wire        flash_miso,")
    a("    output wire        sd_clk, output wire sd_csn, output wire sd_mosi,")
    a("    input  wire        sd_miso, input wire sd_det,")
    a("    output wire        sdram_clk, output wire sdram_cke,")
    a("    output wire        sdram_csn, output wire sdram_rasn,")
    a("    output wire        sdram_casn, output wire sdram_wen,")
    a("    output wire [1:0]  sdram_ba, output wire [12:0] sdram_a,")
    a("    inout  wire [15:0] sdram_dq, output wire [1:0] sdram_dqm")
    a(");")
    a("    assign flash_csn=1; assign flash_mosi=0; assign flash_wpn=1; assign flash_resetn=1;")
    a("    assign sd_clk=0; assign sd_csn=1; assign sd_mosi=1;")
    a("    assign sdram_clk=0; assign sdram_cke=0; assign sdram_csn=1;")
    a("    assign sdram_rasn=1; assign sdram_casn=1; assign sdram_wen=1;")
    a("    assign sdram_ba=0; assign sdram_a=0; assign sdram_dqm=2'b11;")
    a("")
    a("    localparam integer CLK_HZ = 25000000;")
    a("    localparam integer BAUD = 115200;")
    a(f"    localparam integer MEM_WORDS = {mem_words};")
    a("")
    a("    logic sys_clk;")
    a("    always_ff @(posedge clk) begin")
    a("        if (~button[0]) sys_clk <= 0; else sys_clk <= ~sys_clk;")
    a("    end")
    a("    logic [3:0] sc; logic sd;")
    a("    always_ff @(posedge sys_clk) begin")
    a("        if (~button[0]) begin sc<=0; sd<=0; end")
    a("        else if (!sd) begin if (sc==15) sd<=1; else sc<=sc+1; end")
    a("    end")
    a("    wire rst = ~button[0] || !sd;")
    a("")

    # CPU
    a("    wire [31:0] mem_addr, mem_wdata;")
    a("    wire [3:0] mem_wstrb; wire mem_valid;")
    a("    reg [31:0] mem_rdata; reg mem_ready;")
    a("    wire [31:0] dbg_reg10;")
    a("    rime_i_core CPU(.clk(sys_clk),.rst(rst),")
    a("        .mem_addr(mem_addr),.mem_wdata(mem_wdata),")
    a("        .mem_wstrb(mem_wstrb),.mem_valid(mem_valid),")
    a("        .mem_rdata(mem_rdata),.mem_ready(mem_ready),")
    a("        .dbg_reg10(dbg_reg10));")
    a("")

    # Detect DMA modules — if any are present, generate a bus arbiter
    dma_modules = [m for m in plan.modules if m.requires_dma]
    has_dma = len(dma_modules) > 0

    if has_dma:
        a("    // --- Bus arbiter: CPU (priority) + DMA master ---")
        a("    wire [31:0] dma_m_addr; wire dma_m_rd; wire [31:0] dma_m_rdata; wire dma_m_ready;")
        a("    reg dma_grant;")
        a("    wire cpu_active = mem_valid && !mem_ready;")
        a("    wire [31:0] arb_addr  = dma_grant ? dma_m_addr : mem_addr;")
        a("    wire [31:0] arb_wdata = dma_grant ? 32'd0 : mem_wdata;")
        a("    wire [3:0]  arb_wstrb = dma_grant ? 4'd0 : mem_wstrb;")
        a("    wire        arb_valid = dma_grant ? dma_m_rd : mem_valid;")
        a("    assign dma_m_rdata = arb_rdata;")
        a("    assign dma_m_ready = dma_grant && arb_ready;")
        a("    always_ff @(posedge sys_clk) begin")
        a("        if (rst) dma_grant <= 0;")
        a("        else if (!cpu_active && dma_m_rd && !dma_grant) dma_grant <= 1;")
        a("        else if (arb_ready) dma_grant <= 0;")
        a("    end")
        a("")
        bus_addr = "arb_addr"
        bus_wdata = "arb_wdata"
        bus_wstrb = "arb_wstrb"
        bus_valid = "arb_valid"
    else:
        bus_addr = "mem_addr"
        bus_wdata = "mem_wdata"
        bus_wstrb = "mem_wstrb"
        bus_valid = "mem_valid"

    # BRAM
    a("    (* ram_style = \"block\" *)")
    a("    reg [31:0] bram [0:MEM_WORDS-1];")
    a(f"    wire [{max(0, (mem_words-1).bit_length()-1)}:0] bram_idx = {bus_addr}[{max(1, (mem_words-1).bit_length())+1}:2];")
    a(f"    wire is_bram = ({bus_addr}[31:28]==4'h0);")
    a(f"    wire is_uart = ({bus_addr}[31:28]==4'h2);")
    a("")

    # Address decode for each module
    for m in plan.modules:
        nibble = plan.address_map[m.name]
        a(f"    wire is_{m.name} = ({bus_addr}[31:24]==8'h{nibble:02X});")
    a("")

    # BRAM write
    a("    always_ff @(posedge sys_clk) begin")
    a("        if (is_bram && mem_valid && mem_wstrb!=0) begin")
    a("            if (mem_wstrb[0]) bram[bram_idx][7:0]<=mem_wdata[7:0];")
    a("            if (mem_wstrb[1]) bram[bram_idx][15:8]<=mem_wdata[15:8];")
    a("            if (mem_wstrb[2]) bram[bram_idx][23:16]<=mem_wdata[23:16];")
    a("            if (mem_wstrb[3]) bram[bram_idx][31:24]<=mem_wdata[31:24];")
    a("        end")
    a("    end")
    a("    wire [31:0] bram_rdata = bram[bram_idx];")
    a("")

    # UART
    a("    reg tx_send; reg [7:0] tx_byte;")
    a("    reg [15:0] tx_busy_cnt;")
    a("    wire tx_busy = (tx_busy_cnt!=0);")
    a("    localparam integer UCC = ((CLK_HZ/BAUD)*11);")
    a("    uart_tx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) UTX(.clk(sys_clk),.send(tx_send),.data(tx_byte),.tx(usb_tx));")
    a("    always_ff @(posedge sys_clk) begin")
    a("        if (rst) tx_busy_cnt<=0;")
    a("        else if (tx_send) tx_busy_cnt<=UCC[15:0];")
    a("        else if (tx_busy_cnt!=0) tx_busy_cnt<=tx_busy_cnt-1;")
    a("    end")
    a("    wire rx_valid; wire [7:0] rx_data;")
    a("    reg rx_pending; reg [7:0] rx_byte;")
    a("    uart_rx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) URX(.clk(sys_clk),.rx(usb_rx),.finish(rx_valid),.data(rx_data));")
    a("    always_ff @(posedge sys_clk) begin")
    a("        if (rst) rx_pending<=0;")
    a("        else begin")
    a("            if (rx_valid) begin rx_byte<=rx_data; rx_pending<=1; end")
    a("            if (is_uart&&mem_valid&&mem_ready&&mem_wstrb==0&&mem_addr[3:0]==4'h8) rx_pending<=0;")
    a("        end")
    a("    end")
    a("")

    # Module instantiations: each module gets a reg_wr/reg_rd strobe that
    # fires only when (a) the address matches, (b) a valid bus request exists,
    # (c) the bus hasn't already acknowledged this cycle, and
    # (d) the module itself hasn't asserted ready. This prevents double-fire.
    for m in plan.modules:
        a(f"    wire [31:0] {m.name}_rdata; wire {m.name}_ready;")
        wr = f"is_{m.name}&&{bus_valid}&&!mem_ready&&!{m.name}_ready&&{bus_wstrb}!=0"
        rd = f"is_{m.name}&&{bus_valid}&&!mem_ready&&!{m.name}_ready&&{bus_wstrb}==0"
        a(f"    {m.top_module} {m.name.upper()}_MOD(.clk(sys_clk),.rst(rst),")
        if m.requires_snoop:
            a(f"        .snoop_addr({bus_addr}),.snoop_wstrb({bus_wstrb}),.snoop_valid({bus_valid}),.snoop_ready(mem_ready),")
        if m.requires_dma:
            a("        .dma_addr(dma_m_addr),.dma_rd(dma_m_rd),.dma_rdata(dma_m_rdata),.dma_ready(dma_m_ready),")
        a(f"        .reg_addr({bus_addr}[11:0]),.reg_wdata({bus_wdata}),")
        a(f"        .reg_wr({wr}),")
        a(f"        .reg_rd({rd}),")
        a(f"        .reg_rdata({m.name}_rdata),.reg_ready({m.name}_ready));")
        a("")

    # Memory response mux
    if has_dma:
        # arb_rdata and arb_ready: shared response bus for both CPU and DMA master.
        # The module response mux below drives these; the arbiter routes them
        # to mem_rdata/mem_ready (CPU) or dma_m_rdata/dma_m_ready (DMA) based on grant.
        a("    reg [31:0] arb_rdata_r; reg arb_ready_r;")
        a("    wire [31:0] arb_rdata = arb_rdata_r;")
        a("    wire arb_ready = arb_ready_r;")
        a("")

    a("    always_ff @(posedge sys_clk) begin")
    a("        tx_send<=0; mem_ready<=0;")
    if has_dma:
        a("        arb_ready_r<=0;")
    a(f"        if (!rst && {bus_valid} && !mem_ready) begin")
    a("            if (is_bram) begin mem_rdata<=bram_rdata; mem_ready<=1; end")
    a("            else if (is_uart) begin")
    a("                case(mem_addr[3:0])")
    a("                    4'h0: begin")
    a("                        if (mem_wstrb!=0 && !tx_busy) begin tx_byte<=mem_wdata[7:0]; tx_send<=1; mem_ready<=1; end")
    a("                        else if (mem_wstrb==0) begin mem_rdata<=0; mem_ready<=1; end")
    a("                    end")
    a("                    4'h4: begin mem_rdata<={31'd0,tx_busy}; mem_ready<=1; end")
    a("                    4'h8: begin mem_rdata<={24'd0,rx_byte}; mem_ready<=1; end")
    a("                    4'hC: begin mem_rdata<={31'd0,rx_pending}; mem_ready<=1; end")
    a("                    default: begin mem_rdata<=0; mem_ready<=1; end")
    a("                endcase")
    a("            end")
    for m in plan.modules:
        a(f"            else if (is_{m.name}) begin")
        if has_dma:
            a(f"                if ({m.name}_ready) begin arb_rdata_r<={m.name}_rdata; arb_ready_r<=1; if(!dma_grant) begin mem_rdata<={m.name}_rdata; mem_ready<=1; end end")
        else:
            a(f"                if ({m.name}_ready) begin mem_rdata<={m.name}_rdata; mem_ready<=1; end")
        a("            end")
    if has_dma:
        a("            else begin arb_rdata_r<=0; arb_ready_r<=1; if(!dma_grant) begin mem_rdata<=0; mem_ready<=1; end end")
    else:
        a("            else begin mem_rdata<=0; mem_ready<=1; end")
    a("        end")
    a("    end")

    a("    assign led = dbg_reg10[4:0];")

    # BRAM init via $readmemh. The hex file is written alongside top.sv
    # by callers (generate_and_build, or manual scripts).
    a('    initial $readmemh("firmware.hex", bram);')
    a("endmodule")

    return "\n".join(lines) + "\n"


def write_firmware_hex(firmware: list[int], path: Path, *, mem_words: int = 1024) -> None:
    """Write firmware as a hex file for $readmemh BRAM initialization."""
    with open(path, "w", encoding="utf-8") as f:
        for i in range(mem_words):
            if i < len(firmware):
                f.write(f"{firmware[i]:08x}\n")
            else:
                f.write("00000013\n")  # NOP


def generate_and_build(
    module_names: list[str],
    firmware: list[int],
    *,
    output_dir: Path | None = None,
    clean: bool = True,
) -> tuple[CompositionPlan, Path]:
    """Validate, generate top.sv, and build. Returns (plan, bitstream_path)."""
    from icepi.build import build_project

    plan = validate_composition(module_names)

    if output_dir is None:
        if len(module_names) == 1:
            output_dir = MODULES_ROOT / module_names[0]
        else:
            output_dir = MODULES_ROOT / "compositions"
    output_dir.mkdir(parents=True, exist_ok=True)

    top_sv = output_dir / "top.sv"
    top_sv.write_text(compose(plan, firmware), encoding="utf-8")
    write_firmware_hex(firmware, output_dir / "firmware.hex")

    project_name = output_dir.name
    bitstream = build_project(project_name, clean=clean)
    return plan, bitstream
