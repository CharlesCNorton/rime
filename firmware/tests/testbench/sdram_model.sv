// Behavioral SDRAM model for simulation (W9825G6KH-compatible).
// 256 Mbit: 4 banks x 8192 rows x 512 columns x 16 bits.
// Supports: INIT_PRECHARGE, LOAD_MODE, ACTIVATE, READ, WRITE, REFRESH.
// No timing checks — functional correctness only.

module sdram_model (
    input  wire        clk,
    input  wire        cke,
    input  wire        csn,
    input  wire        rasn,
    input  wire        casn,
    input  wire        wen,
    input  wire [1:0]  ba,
    input  wire [12:0] a,
    inout  wire [15:0] dq,
    input  wire [1:0]  dqm
);

    localparam ROWS = 8192;
    localparam COLS = 512;
    localparam BANKS = 4;

    reg [15:0] mem [0:BANKS-1][0:ROWS-1][0:COLS-1];

    reg [12:0] active_row [0:BANKS-1];
    reg        row_open   [0:BANKS-1];
    reg [1:0]  cas_latency;
    reg        burst_type;
    reg [2:0]  burst_len;
    reg        initialized;

    reg [15:0] dq_out;
    reg        dq_oe;
    assign dq = dq_oe ? dq_out : 16'bz;

    // Pipeline read data by CAS latency
    reg [15:0] read_pipe [0:3];
    reg        read_valid_pipe [0:3];
    integer    rp;

    wire [3:0] cmd = {csn, rasn, casn, wen};
    localparam CMD_NOP       = 4'b0111;
    localparam CMD_ACTIVE    = 4'b0011;
    localparam CMD_READ      = 4'b0101;
    localparam CMD_WRITE     = 4'b0100;
    localparam CMD_PRECHARGE = 4'b0010;
    localparam CMD_REFRESH   = 4'b0001;
    localparam CMD_LOAD_MODE = 4'b0000;
    localparam CMD_INHIBIT   = 4'b1111;

    integer i;
    initial begin
        initialized = 0;
        cas_latency = 2;
        burst_type = 0;
        burst_len = 0;
        dq_out = 16'd0;
        dq_oe = 0;
        for (i = 0; i < BANKS; i = i + 1) begin
            row_open[i] = 0;
            active_row[i] = 0;
        end
        for (rp = 0; rp < 4; rp = rp + 1) begin
            read_pipe[rp] = 16'd0;
            read_valid_pipe[rp] = 0;
        end
    end

    always @(posedge clk) begin
        dq_oe <= 0;

        // Shift read pipeline
        read_valid_pipe[3] <= read_valid_pipe[2];
        read_pipe[3]       <= read_pipe[2];
        read_valid_pipe[2] <= read_valid_pipe[1];
        read_pipe[2]       <= read_pipe[1];
        read_valid_pipe[1] <= read_valid_pipe[0];
        read_pipe[1]       <= read_pipe[0];
        read_valid_pipe[0] <= 0;

        // Output from pipeline at CAS latency position
        if (read_valid_pipe[cas_latency]) begin
            dq_out <= read_pipe[cas_latency];
            dq_oe  <= 1;
        end

        if (cke) begin
            case (cmd)
                CMD_LOAD_MODE: begin
                    cas_latency <= a[6:4];
                    burst_len   <= a[2:0];
                    burst_type  <= a[3];
                    initialized <= 1;
                end

                CMD_ACTIVE: begin
                    active_row[ba] <= a;
                    row_open[ba]   <= 1;
                end

                CMD_PRECHARGE: begin
                    if (a[10]) begin
                        for (i = 0; i < BANKS; i = i + 1)
                            row_open[i] <= 0;
                    end else begin
                        row_open[ba] <= 0;
                    end
                end

                CMD_READ: begin
                    if (row_open[ba]) begin
                        read_pipe[0]       <= mem[ba][active_row[ba]][a[8:0]];
                        read_valid_pipe[0] <= 1;
                    end
                end

                CMD_WRITE: begin
                    if (row_open[ba]) begin
                        if (!dqm[0]) mem[ba][active_row[ba]][a[8:0]][7:0]  <= dq[7:0];
                        if (!dqm[1]) mem[ba][active_row[ba]][a[8:0]][15:8] <= dq[15:8];
                    end
                end

                CMD_REFRESH: begin
                    // No-op in behavioral model
                end

                CMD_NOP, CMD_INHIBIT: begin
                    // No-op
                end
            endcase
        end
    end
endmodule
