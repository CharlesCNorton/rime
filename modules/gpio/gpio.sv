// GPIO: General Purpose Input/Output controller
// 16 pins with software-driven direction, output, input simulation,
// and rising-edge interrupt latches. For testing, pins are register-driven
// rather than wired to physical I/O.
//
// Memory map:
//   0x000: DIR     (write/read) — bit i = 1 means pin i is output, 0 means input
//   0x004: OUT     (write/read) — output value for pins where DIR=1
//   0x008: IN      (write/read) — simulated input value (driven by software for testing)
//   0x00C: PIN     (read)       — effective pin state: DIR ? OUT : IN
//   0x010: EDGE    (read)       — sticky rising-edge latches per pin (clears on read)
//   0x014: CONTROL (write)      — bit 0 = clear EDGE latches manually

module gpio (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [15:0] dir;
    logic [15:0] out;
    logic [15:0] in_sim;
    logic [15:0] edge_latch;
    logic [15:0] in_prev;

    wire [15:0] pin = (dir & out) | (~dir & in_sim);
    wire [15:0] rising = pin & ~in_prev;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            dir        <= 16'd0;
            out        <= 16'd0;
            in_sim     <= 16'd0;
            edge_latch <= 16'd0;
            in_prev    <= 16'd0;
        end else begin
            // Sample pin state every cycle, latch rising edges
            in_prev    <= pin;
            edge_latch <= edge_latch | rising;

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: dir    <= reg_wdata[15:0];
                    3'h1: out    <= reg_wdata[15:0];
                    3'h2: in_sim <= reg_wdata[15:0];
                    3'h5: begin
                        if (reg_wdata[0]) edge_latch <= 16'd0;
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {16'd0, dir};
                    3'h1: reg_rdata <= {16'd0, out};
                    3'h2: reg_rdata <= {16'd0, in_sim};
                    3'h3: reg_rdata <= {16'd0, pin};
                    3'h4: begin
                        reg_rdata  <= {16'd0, edge_latch};
                        edge_latch <= 16'd0;
                    end
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
