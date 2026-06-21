// DIVIDE: Direct Integer Variable-length Iterative Division Engine
// 32-bit unsigned integer divider. 32-cycle iterative shift-subtract.
// Write dividend and divisor, poll done, read quotient and remainder.
// Division by zero returns quotient=0xFFFFFFFF, remainder=dividend.
//
// Memory map:
//   0x000: DIVIDEND (write) — 32-bit dividend
//   0x004: DIVISOR  (write) — 32-bit divisor; triggers computation
//   0x008: QUOTIENT (read)  — 32-bit quotient (valid when done)
//   0x00C: REMAIN   (read)  — 32-bit remainder (valid when done)
//   0x010: STATUS   (read)  — bit 0 = done, bit 1 = div-by-zero
//   0x014: CONTROL  (write) — bit 0 = reset

module divide (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // Shift-subtract restoring division: one bit per cycle, MSB first.
    // After 32 iterations, quotient holds the result and remainder the modulus.
    logic [31:0] dividend_reg;
    logic [31:0] divisor_reg;
    logic [31:0] quotient;
    logic [31:0] remainder;
    logic        computing;
    logic        done;
    logic        div_by_zero;
    logic [5:0]  bit_idx;

    logic [31:0] work_dividend;
    logic [32:0] work_remainder;

    // Combinational: compute one division step
    wire [32:0] shifted_rem = {work_remainder[31:0], work_dividend[31]};
    wire [31:0] shifted_div = {work_dividend[30:0], 1'b0};
    wire        sub_ok      = (shifted_rem >= {1'b0, divisor_reg});
    wire [32:0] next_rem    = sub_ok ? (shifted_rem - {1'b0, divisor_reg}) : shifted_rem;
    wire [31:0] next_div    = sub_ok ? (shifted_div | 32'd1) : shifted_div;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            dividend_reg   <= 32'd0;
            divisor_reg    <= 32'd0;
            quotient       <= 32'd0;
            remainder      <= 32'd0;
            computing      <= 1'b0;
            done           <= 1'b0;
            div_by_zero    <= 1'b0;
            bit_idx        <= 6'd0;
            work_dividend  <= 32'd0;
            work_remainder <= 33'd0;
        end else begin
            if (computing) begin
                work_remainder <= next_rem;
                work_dividend  <= next_div;
                if (bit_idx == 6'd31) begin
                    quotient  <= next_div;
                    remainder <= next_rem[31:0];
                    computing <= 1'b0;
                    done      <= 1'b1;
                end
                bit_idx <= bit_idx + 6'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        dividend_reg <= reg_wdata;
                    end
                    3'h1: begin
                        divisor_reg <= reg_wdata;
                        if (reg_wdata == 32'd0) begin
                            quotient    <= 32'hFFFFFFFF;
                            remainder   <= dividend_reg;
                            done        <= 1'b1;
                            div_by_zero <= 1'b1;
                            computing   <= 1'b0;
                        end else begin
                            work_dividend  <= dividend_reg;
                            work_remainder <= 33'd0;
                            bit_idx        <= 6'd0;
                            computing      <= 1'b1;
                            done           <= 1'b0;
                            div_by_zero    <= 1'b0;
                        end
                    end
                    3'h5: begin
                        if (reg_wdata[0]) begin
                            dividend_reg   <= 32'd0;
                            divisor_reg    <= 32'd0;
                            quotient       <= 32'd0;
                            remainder      <= 32'd0;
                            computing      <= 1'b0;
                            done           <= 1'b0;
                            div_by_zero    <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= dividend_reg;
                    3'h1: reg_rdata <= divisor_reg;
                    3'h2: reg_rdata <= quotient;
                    3'h3: reg_rdata <= remainder;
                    3'h4: reg_rdata <= {30'd0, div_by_zero, done};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
