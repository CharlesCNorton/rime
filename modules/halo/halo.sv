// HALO: Hardware Assisted Loop Orchestrator
// 64-entry 32-bit ring ringfer with hardware head/tail, watermark, overflow tracking.
//
// Memory map:
//   0x000: PUSH    (write) — enqueue 32-bit word at head
//   0x004: POP     (read)  — dequeue from tail (advances tail)
//   0x008: PEEK    (read)  — read tail without advancing
//   0x00C: STATUS  (read)  — bit 0=empty, bit 1=full, bit 2=watermark, bit 3=overflow
//   0x010: COUNT   (read)  — current occupancy
//   0x014: CONTROL (write) — bit 0=clear, bits[7:1]=watermark threshold
//   0x018: DROPPED (read)  — number of words dropped due to overflow since last clear

module halo (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);
    localparam DEPTH = 64;
    localparam AW = 6;

    (* ram_style = "distributed" *) logic [31:0] ring [0:DEPTH-1];
    logic [AW:0] head, tail;
    logic [AW:0] occupancy;
    logic [6:0]  watermark;
    logic [15:0] dropped;
    logic        overflow_flag;

    wire empty_w = (head == tail);
    wire full_w  = (occupancy >= DEPTH);
    wire wmark_w = (occupancy >= {1'b0, watermark});

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            head <= 0; tail <= 0; occupancy <= 0;
            watermark <= 7'd48; dropped <= 16'd0; overflow_flag <= 1'b0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        if (!full_w) begin
                            ring[head[AW-1:0]] <= reg_wdata;
                            head <= head + 1;
                            occupancy <= occupancy + 1;
                        end else begin
                            dropped <= dropped + 16'd1;
                            overflow_flag <= 1'b1;
                        end
                    end
                    3'h5: begin
                        if (reg_wdata[0]) begin
                            head <= 0; tail <= 0; occupancy <= 0;
                            dropped <= 16'd0; overflow_flag <= 1'b0;
                        end
                        watermark <= reg_wdata[7:1];
                    end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: begin
                        reg_rdata <= empty_w ? 32'd0 : ring[tail[AW-1:0]];
                        if (!empty_w) begin
                            tail <= tail + 1;
                            occupancy <= occupancy - 1;
                        end
                    end
                    3'h2: reg_rdata <= empty_w ? 32'd0 : ring[tail[AW-1:0]];
                    3'h3: reg_rdata <= {28'd0, overflow_flag, wmark_w, full_w, empty_w};
                    3'h4: reg_rdata <= {25'd0, occupancy};
                    3'h6: reg_rdata <= {16'd0, dropped};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
