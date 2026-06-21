// SIGMA: Fletcher-16 streaming checksum
// Feed bytes, read running checksum at any time.
// Fletcher-16: sum1 += byte, sum2 += sum1, both mod 255.
//
// Memory map:
//   0x000: DATA    (write) — feed one byte
//   0x004: CKSUM   (read)  — Fletcher-16 checksum (sum2<<8 | sum1)
//   0x008: CONTROL (write) — bit 0 = reset
//   0x00C: COUNT   (read)  — bytes fed

module sigma (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0]  sum1, sum2;
    logic [31:0] count;

    // Fletcher-16 step
    wire [8:0] new_sum1 = {1'b0, sum1} + {1'b0, reg_wdata[7:0]};
    wire [7:0] mod_sum1 = (new_sum1 >= 9'd255) ? (new_sum1[7:0] - 8'd255) : new_sum1[7:0];
    wire [8:0] new_sum2 = {1'b0, sum2} + {1'b0, mod_sum1};
    wire [7:0] mod_sum2 = (new_sum2 >= 9'd255) ? (new_sum2[7:0] - 8'd255) : new_sum2[7:0];

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            sum1 <= 8'd0; sum2 <= 8'd0; count <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        sum1 <= mod_sum1;
                        sum2 <= mod_sum2;
                        count <= count + 32'd1;
                    end
                    3'h2: if (reg_wdata[0]) begin sum1<=0; sum2<=0; count<=0; end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {16'd0, sum2, sum1};
                    3'h3: reg_rdata <= count;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
