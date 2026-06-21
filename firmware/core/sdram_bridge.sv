// sdram_bridge: 16-byte bulk SDRAM access bridge.
//
// Converts a single 128-bit (16-byte) read or write into 8 sequential
// 16-bit SDRAM word transactions. Used by rime_service for
// SDRAM_READ16, SDRAM_WRITE16, SDRAM_WRITE_STREAM, and the on-board
// erase/program and verify loops.
//
// Interface:
//   start      — pulse to begin a 16-byte transfer
//   wr         — 1 for write, 0 for read
//   base_addr  — starting word address (8 consecutive words)
//   wdata      — 128-bit write data (big-endian: wdata[127:112] = first word)
//   rdata      — 128-bit read data (same byte order)
//   done       — pulses when all 8 words have been transferred
//   busy       — high while transfer is in progress
//
// Internally sequences 8 req/ack/valid cycles against the SDRAM
// controller, advancing the word address by 1 each step.

module sdram_bridge #(
    parameter integer CLK_HZ = 25000000
) (
    input  wire         clk,
    input  wire         rst,

    input  wire         start,
    input  wire         wr,
    input  wire  [23:0] base_addr,
    input  wire [127:0] wdata,
    output logic [127:0] rdata,
    output logic        done,
    output logic        busy,

    output logic        sdram_req,
    output logic        sdram_wr,
    output logic [23:0] sdram_addr,
    output logic [15:0] sdram_wdata,
    input  wire  [15:0] sdram_rdata,
    input  wire         sdram_ready,
    input  wire         sdram_valid,
    input  wire         sdram_ack
);

    localparam [2:0] S_IDLE    = 3'd0;
    localparam [2:0] S_REQ     = 3'd1;
    localparam [2:0] S_WAIT    = 3'd2;
    localparam [2:0] S_CAPTURE = 3'd3;

    logic [2:0]  state;
    logic        accepted;
    logic [23:0] op_addr;
    logic [2:0]  word_idx;
    logic        op_wr;
    logic [127:0] op_wdata;

    always_ff @(posedge clk) begin
        done     <= 1'b0;
        sdram_req <= 1'b0;

        if (rst) begin
            state    <= S_IDLE;
            accepted <= 1'b0;
            word_idx <= 3'd0;
            op_wr    <= 1'b0;
            op_addr  <= 24'd0;
            op_wdata <= 128'd0;
            rdata    <= 128'd0;
            busy     <= 1'b0;
            sdram_wr    <= 1'b0;
            sdram_addr  <= 24'd0;
            sdram_wdata <= 16'd0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (start) begin
                        op_addr  <= base_addr;
                        op_wr    <= wr;
                        op_wdata <= wdata;
                        word_idx <= 3'd0;
                        busy     <= 1'b1;
                        state    <= S_REQ;
                    end
                end

                S_REQ: begin
                    if (sdram_ready) begin
                        sdram_req   <= 1'b1;
                        sdram_wr    <= op_wr;
                        sdram_addr  <= op_addr;
                        sdram_wdata <= op_wdata[127 - (word_idx * 16) -: 16];
                        accepted    <= 1'b0;
                        state       <= S_WAIT;
                    end
                end

                S_WAIT: begin
                    if (!accepted) begin
                        sdram_req <= 1'b1;
                        sdram_wr  <= op_wr;
                        if (sdram_ack)
                            accepted <= 1'b1;
                    end else begin
                        if (!op_wr && sdram_valid) begin
                            rdata[127 - (word_idx * 16) -: 16] <= sdram_rdata;
                            state <= S_CAPTURE;
                        end else if (op_wr && sdram_ready) begin
                            state <= S_CAPTURE;
                        end
                    end
                end

                S_CAPTURE: begin
                    if (word_idx == 3'd7) begin
                        done  <= 1'b1;
                        busy  <= 1'b0;
                        state <= S_IDLE;
                    end else begin
                        op_addr  <= op_addr + 24'd1;
                        word_idx <= word_idx + 3'd1;
                        state    <= S_REQ;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
