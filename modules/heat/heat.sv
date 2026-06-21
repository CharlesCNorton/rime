// HEAT: Hardware Execution Activity Tracker
// 16-page memory access heatmap. Snoop interface counts bus transactions
// per page region. 8-bit saturating counters in registers.
//
// Memory map:
//   0x000: CONTROL  (write) — bit 0 = enable, bit 1 = clear, bit 2 = freeze
//   0x004: STATUS   (read)  — bit 0 = enabled, bit 1 = any counter saturated
//   0x008: TOTAL    (read)  — 32-bit total transactions since last clear
//   0x040-0x07C: PAGE[0..15] (read) — 8-bit access count per page region

module heat (
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
    logic [7:0]  counters [0:15];
    logic        enabled, frozen;
    logic [31:0] total;
    logic        any_sat;

    wire snoop_fire = snoop_valid && snoop_ready && enabled && !frozen;
    wire [3:0] page_idx = snoop_addr[19:16];

    integer _i;
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            enabled <= 1'b0; frozen <= 1'b0; total <= 32'd0; any_sat <= 1'b0;
            for (_i = 0; _i < 16; _i = _i + 1) counters[_i] <= 8'd0;
        end else begin
            if (snoop_fire) begin
                if (counters[page_idx] < 8'hFF)
                    counters[page_idx] <= counters[page_idx] + 8'd1;
                else
                    any_sat <= 1'b1;
                total <= total + 32'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[7:2] == 6'h00) begin
                    enabled <= reg_wdata[0];
                    if (reg_wdata[1]) begin
                        for (_i = 0; _i < 16; _i = _i + 1) counters[_i] <= 8'd0;
                        total <= 32'd0; any_sat <= 1'b0;
                    end
                    frozen <= reg_wdata[2];
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[7:4] == 4'h0) begin
                    case (reg_addr[3:2])
                        2'h1: reg_rdata <= {30'd0, any_sat, enabled};
                        2'h2: reg_rdata <= total;
                        default: reg_rdata <= 32'd0;
                    endcase
                end else if (reg_addr[7:4] == 4'h1) begin
                    reg_rdata <= {24'd0, counters[reg_addr[5:2]]};
                end else begin
                    reg_rdata <= 32'd0;
                end
            end
        end
    end
endmodule
