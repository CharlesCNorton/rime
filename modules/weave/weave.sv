// WEAVE: Bit-serial arithmetic unit
// Processes 32-bit operands one bit at a time, LSB first.
// Multiply takes 32 cycles but costs ~50 LUTs vs ~2000 for parallel.
// Add/sub take 32 cycles. Shift takes 1 cycle.
//
// Memory map:
//   0x000: OP_A    (write) — 32-bit operand A
//   0x004: OP_B    (write) — 32-bit operand B
//   0x008: COMMAND (write) — 0=add, 1=sub, 2=mul, 3=and, 4=or, 5=xor
//   0x00C: RESULT  (read)  — 32-bit result (valid when done)
//   0x010: STATUS  (read)  — bit 0 = done, bit 1 = busy
//   0x014: CYCLES  (read)  — cycles taken for last operation

module weave (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] op_a, op_b;
    logic [31:0] result;
    logic [63:0] accumulator;  // for multiplication
    logic [31:0] shift_a;      // shifted operand
    logic [5:0]  bit_idx;
    logic        busy;
    logic        done;
    logic [5:0]  cycle_count;
    logic [2:0]  operation;    // current op
    logic        carry;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            op_a <= 32'd0; op_b <= 32'd0;
            result <= 32'd0; accumulator <= 64'd0;
            shift_a <= 32'd0; bit_idx <= 6'd0;
            busy <= 1'b0; done <= 1'b0;
            cycle_count <= 6'd0; carry <= 1'b0;
        end else begin
            if (busy) begin
                cycle_count <= cycle_count + 6'd1;
                case (operation)
                    3'd0, 3'd1: begin // ADD/SUB (bit-serial)
                        logic a_bit, b_bit, sum_bit, new_carry;
                        a_bit = shift_a[0];
                        b_bit = (operation == 3'd1) ? ~op_b[bit_idx] : op_b[bit_idx];
                        // For SUB, add initial carry=1 on first bit
                        if (operation == 3'd1 && bit_idx == 6'd0)
                            {new_carry, sum_bit} = a_bit + b_bit + 1'b1;
                        else
                            {new_carry, sum_bit} = a_bit + b_bit + carry;
                        result[bit_idx] <= sum_bit;
                        carry <= new_carry;
                        shift_a <= {1'b0, shift_a[31:1]};
                        if (bit_idx == 6'd31) begin
                            busy <= 1'b0;
                            done <= 1'b1;
                        end
                        bit_idx <= bit_idx + 6'd1;
                    end
                    3'd2: begin // MUL (shift-and-add)
                        if (op_b[bit_idx])
                            accumulator <= accumulator + ({32'd0, shift_a} << bit_idx);
                        if (bit_idx == 6'd31) begin
                            result <= accumulator[31:0];
                            busy <= 1'b0;
                            done <= 1'b1;
                        end
                        bit_idx <= bit_idx + 6'd1;
                    end
                    3'd3: begin // AND (single cycle)
                        result <= op_a & op_b;
                        busy <= 1'b0; done <= 1'b1;
                    end
                    3'd4: begin // OR
                        result <= op_a | op_b;
                        busy <= 1'b0; done <= 1'b1;
                    end
                    3'd5: begin // XOR
                        result <= op_a ^ op_b;
                        busy <= 1'b0; done <= 1'b1;
                    end
                    default: begin busy <= 1'b0; done <= 1'b1; end
                endcase
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: op_a <= reg_wdata;
                    3'h1: op_b <= reg_wdata;
                    3'h2: begin // COMMAND: start operation
                        operation   <= reg_wdata[2:0];
                        busy        <= 1'b1;
                        done        <= 1'b0;
                        bit_idx     <= 6'd0;
                        cycle_count <= 6'd0;
                        carry       <= 1'b0;
                        shift_a     <= op_a;
                        accumulator <= 64'd0;
                        result      <= 32'd0;
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h3: reg_rdata <= result;
                    3'h4: reg_rdata <= {30'd0, busy, done};
                    3'h5: reg_rdata <= {26'd0, cycle_count};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
