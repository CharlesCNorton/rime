// PYLON: Mailbox FIFO
// 8-deep, 32-bit. Single-FIFO design (one producer, one consumer).
// Producer writes PUSH; consumer reads POP. Both report STATUS bits.
//
// Memory map:
//   0x000: PUSH    (write) — enqueue 32-bit word
//   0x004: POP     (read)  — dequeue 32-bit word (returns 0 if empty)
//   0x008: PEEK    (read)  — read head without removing
//   0x00C: STATUS  (read)  — bit 0 = empty, bit 1 = full, bit 2 = overflow latched
//   0x010: COUNT   (read)  — current FIFO occupancy
//   0x014: CONTROL (write) — bit 0 = clear, bit 1 = clear overflow flag

module pylon (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    localparam DEPTH = 8;
    logic [31:0] fifo [0:DEPTH-1];
    logic [3:0]  head, tail;
    logic [3:0]  count;
    logic        overflow;

    wire empty = (count == 4'd0);
    wire full  = (count == DEPTH[3:0]);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            head <= 4'd0; tail <= 4'd0; count <= 4'd0;
            overflow <= 1'b0;
            for (integer i = 0; i < DEPTH; i = i + 1) fifo[i] <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        if (!full) begin
                            fifo[tail[2:0]] <= reg_wdata;
                            tail <= tail + 4'd1;
                            count <= count + 4'd1;
                        end else begin
                            overflow <= 1'b1;
                        end
                    end
                    3'h5: begin
                        if (reg_wdata[0]) begin
                            head <= 4'd0; tail <= 4'd0; count <= 4'd0;
                            overflow <= 1'b0;
                        end
                        if (reg_wdata[1]) overflow <= 1'b0;
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: begin
                        if (!empty) begin
                            reg_rdata <= fifo[head[2:0]];
                            head <= head + 4'd1;
                            count <= count - 4'd1;
                        end else begin
                            reg_rdata <= 32'd0;
                        end
                    end
                    3'h2: reg_rdata <= empty ? 32'd0 : fifo[head[2:0]];
                    3'h3: reg_rdata <= {29'd0, overflow, full, empty};
                    3'h4: reg_rdata <= {28'd0, count};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
