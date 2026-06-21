// TRACE: on-silicon bus logic analyzer. Captures the first 8 CPU bus
// transactions seen on the passive snoop interface after arm, each tagged
// with a cycle timestamp and the byte-strobe, for host readout and
// waveform/VCD rendering.
//
// Entries are dedicated scalar registers read at fixed offsets (the same
// direct register-read pattern PROFILE uses), not an array, RAM, or packed
// slice — those proved fragile on this toolchain at the compositor's marginal
// sys_clk (bit-bleed / read-latency). Eight entries is a deliberate, robust
// first cut.
//
// Memory map:
//   0x000: CONTROL (write) — bit 0 = arm (reset + capture), bit 1 = stop
//   0x004: COUNT   (read)  — entries captured (0..8)
//   0x008: STATUS  (read)  — bit 0 = capturing, bit 1 = full
//   0x010 + 8*k:   ADDR[k] (read) — snoop_addr of entry k
//   0x014 + 8*k:   META[k] (read) — {timestamp[27:0], wstrb[3:0]} of entry k

module trace (
    input  wire        clk,
    input  wire        rst,

    input  wire [31:0] snoop_addr,
    input  wire [3:0]  snoop_wstrb,
    input  wire        snoop_valid,
    input  wire        snoop_ready,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] a0e, a1e, a2e, a3e, a4e, a5e, a6e, a7e;
    logic [31:0] m0e, m1e, m2e, m3e, m4e, m5e, m6e, m7e;
    logic [3:0]  cidx;        // 0..8
    logic [27:0] ts;
    logic        capturing;
    logic        skip_first;  // drop the arm/control write itself

    wire txn_fire = snoop_valid && snoop_ready;
    wire full     = (cidx >= 4'd8);
    wire [31:0] meta_in = {ts, snoop_wstrb};

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            cidx <= 4'd0; ts <= 28'd0; capturing <= 1'b0; skip_first <= 1'b0;
        end else begin
            if (capturing) begin
                ts <= ts + 28'd1;
                if (txn_fire && skip_first) begin
                    skip_first <= 1'b0;
                end else if (txn_fire && !full) begin
                    case (cidx)
                        4'd0: begin a0e <= snoop_addr; m0e <= meta_in; end
                        4'd1: begin a1e <= snoop_addr; m1e <= meta_in; end
                        4'd2: begin a2e <= snoop_addr; m2e <= meta_in; end
                        4'd3: begin a3e <= snoop_addr; m3e <= meta_in; end
                        4'd4: begin a4e <= snoop_addr; m4e <= meta_in; end
                        4'd5: begin a5e <= snoop_addr; m5e <= meta_in; end
                        4'd6: begin a6e <= snoop_addr; m6e <= meta_in; end
                        4'd7: begin a7e <= snoop_addr; m7e <= meta_in; end
                        default: ;
                    endcase
                    cidx <= cidx + 4'd1;
                end
                if (full) capturing <= 1'b0;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6:2] == 5'd0) begin
                    if (reg_wdata[0]) begin cidx <= 4'd0; ts <= 28'd0; capturing <= 1'b1; skip_first <= 1'b1; end
                    if (reg_wdata[1]) capturing <= 1'b0;
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[6:2])
                    5'd1:  reg_rdata <= {28'd0, cidx};
                    5'd2:  reg_rdata <= {30'd0, full, capturing};
                    5'd4:  reg_rdata <= a0e;   5'd5:  reg_rdata <= m0e;
                    5'd6:  reg_rdata <= a1e;   5'd7:  reg_rdata <= m1e;
                    5'd8:  reg_rdata <= a2e;   5'd9:  reg_rdata <= m2e;
                    5'd10: reg_rdata <= a3e;   5'd11: reg_rdata <= m3e;
                    5'd12: reg_rdata <= a4e;   5'd13: reg_rdata <= m4e;
                    5'd14: reg_rdata <= a5e;   5'd15: reg_rdata <= m5e;
                    5'd16: reg_rdata <= a6e;   5'd17: reg_rdata <= m6e;
                    5'd18: reg_rdata <= a7e;   5'd19: reg_rdata <= m7e;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
