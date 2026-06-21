// PROFILE: on-silicon execution profiler. Taps the CPU bus through the
// passive snoop interface and counts cycles and completed bus transactions
// by direction and address region while active, so a host can read back an
// execution profile of a firmware workload run between start and stop.
//
// Memory map:
//   0x000: CONTROL (write) — bit 0 = start (reset counters + run), bit 1 = stop
//   0x004: CYCLES  (read)  — clock cycles counted while active
//   0x008: TXNS    (read)  — completed bus transactions
//   0x00C: READS   (read)  — transactions with wstrb == 0
//   0x010: WRITES  (read)  — transactions with wstrb != 0
//   0x014: BRAM    (read)  — transactions to 0x0xxxxxxx (code/data RAM)
//   0x018: UART    (read)  — transactions to 0x2xxxxxxx
//   0x01C: MODBUS  (read)  — transactions to 0x3xxxxxxx (module region)
//   0x020: STATUS  (read)  — bit 0 = active

module profile (
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

    logic        active;
    logic [31:0] cycles, txns, reads, writes, c_bram, c_uart, c_mod;

    wire txn_fire = snoop_valid && snoop_ready;
    wire is_wr    = (snoop_wstrb != 4'b0000);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            active <= 1'b0;
            cycles <= 32'd0; txns <= 32'd0; reads <= 32'd0; writes <= 32'd0;
            c_bram <= 32'd0; c_uart <= 32'd0; c_mod <= 32'd0;
        end else begin
            if (active) begin
                cycles <= cycles + 32'd1;
                if (txn_fire) begin
                    txns <= txns + 32'd1;
                    if (is_wr) writes <= writes + 32'd1;
                    else       reads  <= reads  + 32'd1;
                    case (snoop_addr[31:28])
                        4'h0: c_bram <= c_bram + 32'd1;
                        4'h2: c_uart <= c_uart + 32'd1;
                        4'h3: c_mod  <= c_mod  + 32'd1;
                        default: ;
                    endcase
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[5:2] == 4'h0) begin
                    if (reg_wdata[0]) begin
                        active <= 1'b1;
                        cycles <= 32'd0; txns <= 32'd0; reads <= 32'd0; writes <= 32'd0;
                        c_bram <= 32'd0; c_uart <= 32'd0; c_mod <= 32'd0;
                    end
                    if (reg_wdata[1]) active <= 1'b0;
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h1: reg_rdata <= cycles;
                    4'h2: reg_rdata <= txns;
                    4'h3: reg_rdata <= reads;
                    4'h4: reg_rdata <= writes;
                    4'h5: reg_rdata <= c_bram;
                    4'h6: reg_rdata <= c_uart;
                    4'h7: reg_rdata <= c_mod;
                    4'h8: reg_rdata <= {31'd0, active};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
