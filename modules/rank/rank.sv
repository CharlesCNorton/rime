// RANK: Rapid Associative Numerical Keyed sorter
// 8-element sorting network. Write 8 unsigned 32-bit values, trigger sort,
// read them back in ascending order. Uses a Batcher odd-even merge network
// (fixed comparator-swap pairs, constant time, no data-dependent branching).
//
// Memory map:
//   0x000-0x01C: INPUT[0..7]  (write) — 8 unsorted 32-bit values
//   0x020-0x03C: OUTPUT[0..7] (read)  — sorted ascending
//   0x040:       CONTROL       (write) — bit 0 = sort, bit 1 = reset
//   0x044:       STATUS        (read)  — bit 0 = done

module rank (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] data [0:7];
    logic [31:0] sorted [0:7];
    logic        done;

    // Combinational comparator-swap
    function automatic [63:0] cmp_swap(input [31:0] a, input [31:0] b);
        if (a <= b) cmp_swap = {a, b};
        else        cmp_swap = {b, a};
    endfunction

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            done <= 1'b0;
            for (integer i = 0; i < 8; i = i + 1) begin
                data[i]   <= 32'd0;
                sorted[i] <= 32'd0;
            end
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b0) begin
                    data[reg_addr[4:2]] <= reg_wdata;
                end else if (reg_addr[6:2] == 5'h10) begin
                    if (reg_wdata[1]) begin
                        done <= 1'b0;
                        for (integer i = 0; i < 8; i = i + 1) begin
                            data[i]   <= 32'd0;
                            sorted[i] <= 32'd0;
                        end
                    end
                    if (reg_wdata[0]) begin
                        // Batcher odd-even merge sort network for 8 elements
                        // 6 stages, 19 comparator-swap pairs
                        logic [31:0] s [0:7];
                        logic [63:0] pair;
                        for (integer i = 0; i < 8; i = i + 1) s[i] = data[i];

                        // Stage 1: pairs (0,1)(2,3)(4,5)(6,7)
                        pair = cmp_swap(s[0],s[1]); s[0]=pair[63:32]; s[1]=pair[31:0];
                        pair = cmp_swap(s[2],s[3]); s[2]=pair[63:32]; s[3]=pair[31:0];
                        pair = cmp_swap(s[4],s[5]); s[4]=pair[63:32]; s[5]=pair[31:0];
                        pair = cmp_swap(s[6],s[7]); s[6]=pair[63:32]; s[7]=pair[31:0];
                        // Stage 2: pairs (0,2)(1,3)(4,6)(5,7)
                        pair = cmp_swap(s[0],s[2]); s[0]=pair[63:32]; s[2]=pair[31:0];
                        pair = cmp_swap(s[1],s[3]); s[1]=pair[63:32]; s[3]=pair[31:0];
                        pair = cmp_swap(s[4],s[6]); s[4]=pair[63:32]; s[6]=pair[31:0];
                        pair = cmp_swap(s[5],s[7]); s[5]=pair[63:32]; s[7]=pair[31:0];
                        // Stage 3: pairs (1,2)(5,6)
                        pair = cmp_swap(s[1],s[2]); s[1]=pair[63:32]; s[2]=pair[31:0];
                        pair = cmp_swap(s[5],s[6]); s[5]=pair[63:32]; s[6]=pair[31:0];
                        // Stage 4: pairs (0,4)(1,5)(2,6)(3,7)
                        pair = cmp_swap(s[0],s[4]); s[0]=pair[63:32]; s[4]=pair[31:0];
                        pair = cmp_swap(s[1],s[5]); s[1]=pair[63:32]; s[5]=pair[31:0];
                        pair = cmp_swap(s[2],s[6]); s[2]=pair[63:32]; s[6]=pair[31:0];
                        pair = cmp_swap(s[3],s[7]); s[3]=pair[63:32]; s[7]=pair[31:0];
                        // Stage 5: pairs (2,4)(3,5)
                        pair = cmp_swap(s[2],s[4]); s[2]=pair[63:32]; s[4]=pair[31:0];
                        pair = cmp_swap(s[3],s[5]); s[3]=pair[63:32]; s[5]=pair[31:0];
                        // Stage 6: pairs (1,2)(3,4)(5,6)
                        pair = cmp_swap(s[1],s[2]); s[1]=pair[63:32]; s[2]=pair[31:0];
                        pair = cmp_swap(s[3],s[4]); s[3]=pair[63:32]; s[4]=pair[31:0];
                        pair = cmp_swap(s[5],s[6]); s[5]=pair[63:32]; s[6]=pair[31:0];

                        for (integer i = 0; i < 8; i = i + 1) sorted[i] = s[i];
                        done <= 1'b1;
                    end
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b0)
                    reg_rdata <= data[reg_addr[4:2]];
                else if (reg_addr[6] == 1'b0 && reg_addr[5] == 1'b1)
                    reg_rdata <= sorted[reg_addr[4:2]];
                else if (reg_addr[6:2] == 5'h11)
                    reg_rdata <= {31'd0, done};
                else
                    reg_rdata <= 32'd0;
            end
        end
    end
endmodule
