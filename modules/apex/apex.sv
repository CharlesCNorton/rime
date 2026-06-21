// APEX: Asynchronous Priority Evaluation matriX
// 16-entry hardware priority queue. Parallel comparators find the
// insertion point combinationally; the always_ff block shifts and
// inserts in one cycle. Pop shifts all entries up by one.
//
// Memory map:
//   0x000: PUSH_VAL  (write) — stage 32-bit value for next push
//   0x004: PUSH_PRI  (write) — 16-bit priority; triggers insertion
//   0x008: POP_VAL   (read)  — dequeue top entry (removes it)
//   0x00C: PEEK_VAL  (read)  — top value without removal
//   0x010: PEEK_PRI  (read)  — top priority without removal
//   0x014: COUNT     (read)  — current occupancy (0-16)
//   0x018: CONTROL   (write) — bit 0 = clear, bit 1 = min mode
//   0x01C: STATUS    (read)  — bit 0 = empty, bit 1 = full, bit 2 = min_mode

module apex (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    localparam DEPTH = 16;

    logic [31:0] val   [0:DEPTH-1];
    logic [15:0] pri   [0:DEPTH-1];
    logic [4:0]  count;
    logic        min_mode;
    logic [31:0] push_val_staged;

    wire empty_w = (count == 5'd0);
    wire full_w  = (count >= DEPTH);

    // Combinational: find insertion index for a new priority.
    // Scans from high index to low so the LAST (lowest-index) match wins.
    wire [15:0] new_pri_w = reg_wdata[15:0];
    reg [4:0] insert_idx;
    integer _ci;
    always_comb begin
        insert_idx = count < DEPTH ? count[4:0] : 5'd15;
        for (_ci = DEPTH - 1; _ci >= 0; _ci = _ci - 1) begin
            if (_ci[4:0] < count) begin
                if (min_mode ? (new_pri_w < pri[_ci]) : (new_pri_w > pri[_ci]))
                    insert_idx = _ci[4:0];
            end
        end
    end

    integer _i;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            count    <= 5'd0;
            min_mode <= 1'b0;
            push_val_staged <= 32'd0;
            for (_i = 0; _i < DEPTH; _i = _i + 1) begin
                val[_i] <= 32'd0;
                pri[_i] <= 16'd0;
            end
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: push_val_staged <= reg_wdata;
                    3'h1: begin
                        // Push: shift down, insert at insert_idx
                        for (_i = DEPTH - 1; _i > 0; _i = _i - 1) begin
                            if (_i[4:0] > insert_idx) begin
                                val[_i] <= val[_i - 1];
                                pri[_i] <= pri[_i - 1];
                            end
                        end
                        val[insert_idx] <= push_val_staged;
                        pri[insert_idx] <= new_pri_w;
                        if (count < DEPTH)
                            count <= count + 5'd1;
                    end
                    3'h6: begin
                        if (reg_wdata[0]) begin
                            for (_i = 0; _i < DEPTH; _i = _i + 1) begin
                                val[_i] <= 32'd0;
                                pri[_i] <= 16'd0;
                            end
                            count <= 5'd0;
                        end
                        min_mode <= reg_wdata[1];
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: begin
                        reg_rdata <= val[0];
                        for (_i = 0; _i < DEPTH - 1; _i = _i + 1) begin
                            val[_i] <= val[_i + 1];
                            pri[_i] <= pri[_i + 1];
                        end
                        val[DEPTH-1] <= 32'd0;
                        pri[DEPTH-1] <= 16'd0;
                        if (count > 5'd0)
                            count <= count - 5'd1;
                    end
                    3'h3: reg_rdata <= val[0];
                    3'h4: reg_rdata <= {16'd0, pri[0]};
                    3'h5: reg_rdata <= {27'd0, count};
                    3'h7: reg_rdata <= {29'd0, min_mode, full_w, empty_w};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
