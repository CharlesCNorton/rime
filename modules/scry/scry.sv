// SCRY: Silicon Capture for Runtime introspectY
// Circular trace buffer that passively records CPU bus transactions.
//
// Memory map (active port, region 0x3xxxxxxx):
//   0x000: COUNT     (read)  — total captured transactions (saturates at 256)
//   0x004: CONTROL   (write) — bit 0 = enable, bit 1 = clear
//   0x008: WRITE_PTR (read)  — current write index (0-255)
//   0x400-0x7FF: TRACE[0..255] (read) — captured addresses, oldest first
//
// Snoop port is passive: taps every completed bus transaction when enabled.
// 256-entry circular buffer in distributed RAM (~256 LUTs for storage).

module scry (
    input  wire        clk,
    input  wire        rst,

    // Passive snoop on CPU memory bus
    input  wire [31:0] snoop_addr,
    input  wire [3:0]  snoop_wstrb,
    input  wire        snoop_valid,
    input  wire        snoop_ready,

    // Active register port
    input  wire [11:0] reg_addr,   // byte address within SCRY region
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    (* ram_style = "distributed" *) logic [31:0] trace [0:255];
    logic [7:0]  wr_ptr;
    logic [8:0]  count;    // 0..256
    logic        enable;

    wire snoop_fire = snoop_valid && snoop_ready && enable;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            wr_ptr <= 8'd0;
            count  <= 9'd0;
            enable <= 1'b0;
        end else begin
            // Record completed transactions
            if (snoop_fire) begin
                trace[wr_ptr] <= snoop_addr;
                wr_ptr <= wr_ptr + 8'd1;
                if (count < 9'd256)
                    count <= count + 9'd1;
            end

            // Register access
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:2] == 10'h001) begin // 0x004 = CONTROL
                    enable <= reg_wdata[0];
                    if (reg_wdata[1]) begin
                        wr_ptr <= 8'd0;
                        count  <= 9'd0;
                    end
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[11:10] == 2'b00) begin
                    // 0x000-0x3FF: control registers
                    case (reg_addr[3:2])
                        2'h0: reg_rdata <= {23'd0, count};
                        2'h1: reg_rdata <= {31'd0, enable};
                        2'h2: reg_rdata <= {24'd0, wr_ptr};
                        default: reg_rdata <= 32'd0;
                    endcase
                end else begin
                    // 0x400-0x7FF: trace[0..255] = reg_addr[9:2]
                    reg_rdata <= trace[reg_addr[9:2]];
                end
            end
        end
    end
endmodule
