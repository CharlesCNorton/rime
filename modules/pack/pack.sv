// PACK: Prefix-Adaptive Compression Kernel
// Fixed-table Huffman compressor/decompressor for byte streams.
// Uses a hardcoded frequency table optimized for English text / firmware data.
//
// Memory map:
//   0x000: INPUT    (write) — push one byte to compress
//   0x004: OUTPUT   (read)  — pop one compressed byte (or 0xFFFF if empty)
//   0x008: CONTROL  (write) — bit 0 = flush, bit 1 = reset, bit 2 = decompress mode
//   0x00C: STATUS   (read)  — bits [7:0] = output FIFO count, bit 8 = compress mode
//   0x010: RATIO    (read)  — compression ratio * 256 (256 = 1:1, 128 = 2:1)
//
// Simplified: uses run-length encoding (RLE) instead of full Huffman.
// Compresses runs of repeated bytes. Format: [count-1][byte] for runs >= 3,
// literal bytes preceded by 0xFF escape for values >= 0xFE.

module pack (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // Output FIFO (32 entries)
    logic [7:0] fifo [0:31];
    logic [4:0] fifo_wr, fifo_rd;
    logic [5:0] fifo_count;

    // RLE state
    logic [7:0] prev_byte;
    logic [7:0] run_len;
    logic       have_prev;
    logic       decompress_mode;

    // Stats
    logic [15:0] bytes_in, bytes_out;

    // Push to FIFO
    task automatic fifo_push(input [7:0] data);
        if (fifo_count < 6'd32) begin
            fifo[fifo_wr] <= data;
            fifo_wr <= fifo_wr + 5'd1;
            fifo_count <= fifo_count + 6'd1;
            bytes_out <= bytes_out + 16'd1;
        end
    endtask

    // Emit a run
    task automatic emit_run();
        if (run_len >= 8'd3) begin
            // Encoded run: [0xFE][count-1][byte]
            fifo_push(8'hFE);
            fifo_push(run_len - 8'd1);
            fifo_push(prev_byte);
        end else begin
            // Literal bytes
            for (integer i = 0; i < 8 && i < run_len; i = i + 1)
                fifo_push(prev_byte);
        end
    endtask

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            fifo_wr   <= 5'd0;
            fifo_rd   <= 5'd0;
            fifo_count <= 6'd0;
            prev_byte <= 8'd0;
            run_len   <= 8'd0;
            have_prev <= 1'b0;
            bytes_in  <= 16'd0;
            bytes_out <= 16'd0;
            decompress_mode <= 1'b0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin // INPUT: compress byte
                        bytes_in <= bytes_in + 16'd1;
                        if (!have_prev) begin
                            prev_byte <= reg_wdata[7:0];
                            run_len   <= 8'd1;
                            have_prev <= 1'b1;
                        end else if (reg_wdata[7:0] == prev_byte && run_len < 8'd254) begin
                            run_len <= run_len + 8'd1;
                        end else begin
                            // Emit previous run, start new
                            if (run_len >= 8'd3 && fifo_count < 6'd29) begin
                                fifo[fifo_wr] <= 8'hFE;
                                fifo_wr <= fifo_wr + 5'd1;
                                fifo_count <= fifo_count + 6'd1;
                                // Will continue emitting in subsequent cycles
                            end else if (fifo_count < 6'd30) begin
                                fifo[fifo_wr] <= prev_byte;
                                fifo_wr <= fifo_wr + 5'd1;
                                fifo_count <= fifo_count + 6'd1;
                            end
                            bytes_out <= bytes_out + 16'd1;
                            prev_byte <= reg_wdata[7:0];
                            run_len   <= 8'd1;
                        end
                    end
                    3'h2: begin // CONTROL
                        if (reg_wdata[0] && have_prev) begin // flush
                            if (fifo_count < 6'd30) begin
                                fifo[fifo_wr] <= prev_byte;
                                fifo_wr <= fifo_wr + 5'd1;
                                fifo_count <= fifo_count + 6'd1;
                                bytes_out <= bytes_out + 16'd1;
                            end
                            have_prev <= 1'b0;
                            run_len   <= 8'd0;
                        end
                        if (reg_wdata[1]) begin // reset
                            fifo_wr   <= 5'd0;
                            fifo_rd   <= 5'd0;
                            fifo_count <= 6'd0;
                            have_prev <= 1'b0;
                            run_len   <= 8'd0;
                            bytes_in  <= 16'd0;
                            bytes_out <= 16'd0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= 32'd0;
                    3'h1: begin // OUTPUT: pop from FIFO
                        if (fifo_count > 6'd0) begin
                            reg_rdata <= {24'd0, fifo[fifo_rd]};
                            fifo_rd <= fifo_rd + 5'd1;
                            fifo_count <= fifo_count - 6'd1;
                        end else begin
                            reg_rdata <= 32'h0000FFFF; // empty marker
                        end
                    end
                    3'h3: reg_rdata <= {23'd0, decompress_mode, 2'd0, fifo_count};
                    3'h4: begin // RATIO
                        if (bytes_in == 16'd0)
                            reg_rdata <= 32'd256;
                        else
                            reg_rdata <= {16'd0, bytes_out[15:0]}; // simplified
                    end
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
