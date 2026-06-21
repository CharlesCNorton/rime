// ECHO: Event Capture and Hardware Observer
// Cycle-stamped bus transaction logger. 16-entry circular buffer.
// Each entry: {cycle_count[23:0], addr[7:0]} packed into 32 bits.
//
// Memory map:
//   0x000: CONTROL  (write) — bit 0 = enable, bit 1 = clear
//   0x004: STATUS   (read)  — bit 0 = enabled, bit 1 = wrapped
//   0x008: COUNT    (read)  — events captured (0-16)
//   0x00C: CYCLE    (read)  — current 32-bit cycle counter
//   0x010: WR_PTR   (read)  — current write index
//   0x040-0x07C: LOG[0..15] (read) — captured events

module echo (
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
    localparam DEPTH = 16;

    logic [31:0] log_buf [0:DEPTH-1];
    logic [3:0]  wr_ptr;
    logic [4:0]  count;
    logic [31:0] cycle_cnt;
    logic        enabled, wrapped;

    wire snoop_fire = snoop_valid && snoop_ready && enabled;

    integer _i;
    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            wr_ptr <= 4'd0; count <= 5'd0; cycle_cnt <= 32'd0;
            enabled <= 1'b0; wrapped <= 1'b0;
            for (_i = 0; _i < DEPTH; _i = _i + 1) log_buf[_i] <= 32'd0;
        end else begin
            cycle_cnt <= cycle_cnt + 32'd1;

            if (snoop_fire) begin
                log_buf[wr_ptr] <= {cycle_cnt[23:0], snoop_addr[7:0]};
                if (wr_ptr == DEPTH - 1) begin
                    wr_ptr <= 4'd0;
                    wrapped <= 1'b1;
                end else begin
                    wr_ptr <= wr_ptr + 4'd1;
                end
                if (count < DEPTH)
                    count <= count + 5'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[7:2] == 6'h00) begin
                    enabled <= reg_wdata[0];
                    if (reg_wdata[1]) begin
                        wr_ptr <= 4'd0; count <= 5'd0; wrapped <= 1'b0;
                        for (_i = 0; _i < DEPTH; _i = _i + 1) log_buf[_i] <= 32'd0;
                    end
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[7:4] == 4'h0) begin
                    case (reg_addr[3:2])
                        2'h1: reg_rdata <= {30'd0, wrapped, enabled};
                        2'h2: reg_rdata <= {27'd0, count};
                        2'h3: reg_rdata <= cycle_cnt;
                        default: reg_rdata <= 32'd0;
                    endcase
                end else if (reg_addr[7:4] == 4'h1) begin
                    reg_rdata <= log_buf[reg_addr[5:2]];
                end else begin
                    reg_rdata <= 32'd0;
                end
            end
        end
    end
endmodule
