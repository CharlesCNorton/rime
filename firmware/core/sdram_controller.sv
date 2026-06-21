// sdram_controller: single-word SDR SDRAM controller for W9825G6KH.
//
// Handles power-on init (200 us wait, precharge-all, 2x auto-refresh,
// mode-register set), periodic refresh, and single-word read/write
// with row tracking. Addresses the full 32 MB: 4 banks, 8192 rows,
// 512 columns, 16-bit data.
//
// Address mapping (24-bit word address):
//   [23:22] = bank (2 bits, 4 banks)
//   [21:9]  = row  (13 bits, 8192 rows)
//   [8:0]   = column (9 bits, 512 columns)
//
// Interface contract:
//   Assert req with addr, wr, wdata. Controller pulses ack when the
//   request is accepted. For reads, valid pulses one cycle later with
//   rdata. ready indicates the controller can accept a new request.
//   Refresh preempts pending requests and temporarily deasserts ready.
//
// The row-open cache tracks one open row per access. A row miss
// triggers precharge → activate → read/write. Always precharges
// before activate regardless of row_open state to reset the SDRAM's
// internal row latch (required for correct operation on this chip).
//
// CAS latency 2, burst length 1. sdram_clk is the inverted system
// clock to meet hold-time requirements on the SDRAM data bus.

module sdram_controller #(
    parameter integer CLK_HZ = 25000000
) (
    input  wire        clk,
    input  wire        rst,

    input  wire        req,
    input  wire        wr,
    input  wire [23:0] addr,
    input  wire [15:0] wdata,
    output logic [15:0] rdata,
    output logic       ready,
    output logic       valid,
    output logic       ack,
    output logic       init_done,
    output logic [12:0] dbg_last_write_a,
    output logic [1:0]  dbg_last_write_ba,
    output logic [23:0] dbg_last_req_addr,

    output wire        sdram_clk,
    output logic       sdram_cke,
    output logic       sdram_csn,
    output logic       sdram_rasn,
    output logic       sdram_casn,
    output logic       sdram_wen,
    output logic [1:0] sdram_ba,
    output logic [12:0] sdram_a,
    output logic [15:0] sdram_dq_out,
    input  wire  [15:0] sdram_dq_in,
    output logic       sdram_dq_oe,
    output logic [1:0] sdram_dqm
);

    localparam integer INIT_CYCLES      = CLK_HZ / 5000;
    localparam integer T_RCD            = 1;
    localparam integer T_RP             = 1;
    localparam integer T_RFC            = 2;
    localparam integer T_MRD            = 2;
    localparam integer T_WR             = 1;
    localparam integer CAS_LATENCY      = 2;
    localparam integer REFRESH_INTERVAL = ( CLK_HZ / 10000) * 78 / 1000;

    localparam [12:0] MODE_REG = 13'b000_1_00_010_0_000;

    localparam [3:0] SCMD_NOP       = 4'b0111;
    localparam [3:0] SCMD_ACTIVE    = 4'b0011;
    localparam [3:0] SCMD_READ      = 4'b0101;
    localparam [3:0] SCMD_WRITE     = 4'b0100;
    localparam [3:0] SCMD_PRECHARGE = 4'b0010;
    localparam [3:0] SCMD_REFRESH   = 4'b0001;
    localparam [3:0] SCMD_LOAD_MODE = 4'b0000;
    localparam [3:0] SCMD_INHIBIT   = 4'b1111;

    localparam [4:0] ST_INIT_WAIT      = 5'd0;
    localparam [4:0] ST_INIT_PRECHARGE = 5'd1;
    localparam [4:0] ST_INIT_PRE_WAIT  = 5'd2;
    localparam [4:0] ST_INIT_REFRESH1  = 5'd3;
    localparam [4:0] ST_INIT_REF1_WAIT = 5'd4;
    localparam [4:0] ST_INIT_REFRESH2  = 5'd5;
    localparam [4:0] ST_INIT_REF2_WAIT = 5'd6;
    localparam [4:0] ST_INIT_MODE      = 5'd7;
    localparam [4:0] ST_INIT_MODE_WAIT = 5'd8;
    localparam [4:0] ST_IDLE           = 5'd9;
    localparam [4:0] ST_REFRESH        = 5'd10;
    localparam [4:0] ST_REFRESH_WAIT   = 5'd11;
    localparam [4:0] ST_ACTIVATE       = 5'd12;
    localparam [4:0] ST_ACT_WAIT       = 5'd13;
    localparam [4:0] ST_READ_CMD       = 5'd14;
    localparam [4:0] ST_READ_CAS       = 5'd15;
    localparam [4:0] ST_READ_CAPTURE   = 5'd16;
    localparam [4:0] ST_WRITE_CMD      = 5'd17;
    localparam [4:0] ST_WRITE_RECOVERY = 5'd18;
    localparam [4:0] ST_PRECHARGE      = 5'd19;
    localparam [4:0] ST_PRECHARGE_WAIT = 5'd20;

    logic [4:0]  state;
    logic [15:0] init_counter;
    logic [2:0]  wait_counter;
    logic [15:0] refresh_counter;
    logic        refresh_pending;

    logic        req_wr;
    logic [23:0] req_addr;
    logic [15:0] req_wdata;

    logic        row_open;
    logic [1:0]  open_bank;
    logic [12:0] open_row;

    wire [1:0]  req_bank = req_addr[23:22];
    wire [12:0] req_row  = req_addr[21:9];
    wire [8:0]  req_col  = req_addr[8:0];
    logic [12:0] sdram_a_int;
    wire        row_hit  = row_open && (req_bank == open_bank) && (req_row == open_row);

    // SDRAM clock is the inverted system clock. This provides ~half-period
    // of setup time for the DQ bus relative to the controller's posedge.
    assign sdram_clk = ~clk;

    // No byte masking — all 16 bits always active
    assign sdram_dqm = 2'b00;

    always_ff @(posedge clk) begin
        fire_activate <= 1'b0;
        valid <= 1'b0;
        ack   <= 1'b0;

        if (rst) begin
            state           <= ST_INIT_WAIT;
            init_counter    <= 16'd0;
            wait_counter    <= 3'd0;
            refresh_counter <= 16'd0;
            refresh_pending <= 1'b0;
            ready           <= 1'b0;
            init_done       <= 1'b0;
            fire_activate   <= 1'b0;
            sdram_cke       <= 1'b1;
            sdram_dq_oe     <= 1'b0;
            sdram_dq_out    <= 16'd0;
            sdram_ba        <= 2'b00;
            sdram_a_int     <= 13'd0;
            rdata           <= 16'd0;
            req_wr          <= 1'b0;
            req_addr        <= 24'd0;
            req_wdata       <= 16'd0;
            row_open        <= 1'b0;
            open_bank       <= 2'b00;
            open_row        <= 13'd0;
            {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_INHIBIT;
        end else begin
            {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_NOP;
            sdram_dq_oe  <= 1'b0;
            sdram_dq_out <= 16'd0;

            if (init_done) begin
                if (refresh_counter >= REFRESH_INTERVAL[15:0]) begin
                    refresh_counter <= 16'd0;
                    refresh_pending <= 1'b1;
                end else begin
                    refresh_counter <= refresh_counter + 16'd1;
                end
            end

            case (state)
                // --- SDRAM power-on init: 200 us wait → precharge-all → 2x refresh → mode register ---
                ST_INIT_WAIT: begin
                    // JEDEC requires 200 us after power stable before any command
                    sdram_cke <= 1'b1;
                    if (init_counter >= INIT_CYCLES[15:0])
                        state <= ST_INIT_PRECHARGE;
                    else
                        init_counter <= init_counter + 16'd1;
                end

                ST_INIT_PRECHARGE: begin
                    // Precharge all banks (A10=1 selects all-bank precharge)
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_PRECHARGE;
                    sdram_a_int    <= 13'd0;
                    sdram_a_int[10] <= 1'b1;
                    state      <= ST_INIT_PRE_WAIT;
                    wait_counter <= T_RP[2:0];
                end

                ST_INIT_PRE_WAIT: begin
                    if (wait_counter <= 3'd1)
                        state <= ST_INIT_REFRESH1;
                    else
                        wait_counter <= wait_counter - 3'd1;
                end

                ST_INIT_REFRESH1: begin
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_REFRESH;
                    state        <= ST_INIT_REF1_WAIT;
                    wait_counter <= T_RFC[2:0];
                end

                ST_INIT_REF1_WAIT: begin
                    if (wait_counter <= 3'd1)
                        state <= ST_INIT_REFRESH2;
                    else
                        wait_counter <= wait_counter - 3'd1;
                end

                ST_INIT_REFRESH2: begin
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_REFRESH;
                    state        <= ST_INIT_REF2_WAIT;
                    wait_counter <= T_RFC[2:0];
                end

                ST_INIT_REF2_WAIT: begin
                    if (wait_counter <= 3'd1)
                        state <= ST_INIT_MODE;
                    else
                        wait_counter <= wait_counter - 3'd1;
                end

                ST_INIT_MODE: begin
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_LOAD_MODE;
                    sdram_ba     <= 2'b00;
                    sdram_a_int  <= MODE_REG;
                    state        <= ST_INIT_MODE_WAIT;
                    wait_counter <= T_MRD[2:0];
                end

                ST_INIT_MODE_WAIT: begin
                    if (wait_counter <= 3'd1) begin
                        state     <= ST_IDLE;
                        init_done <= 1'b1;
                        ready     <= 1'b1;
                    end else begin
                        wait_counter <= wait_counter - 3'd1;
                    end
                end

                // --- Normal operation: refresh takes priority over data access ---
                ST_IDLE: begin
                    if (refresh_pending) begin
                        ready <= 1'b0;
                        row_open <= 1'b0;  // refresh closes all rows
                        {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_REFRESH;
                        refresh_pending <= 1'b0;
                        state        <= ST_REFRESH_WAIT;
                        wait_counter <= T_RFC[2:0];
                    end else if (req && ready) begin
                        req_wr    <= wr;
                        req_addr  <= addr;
                        req_wdata <= wdata;
                        ready     <= 1'b0;
                        ack       <= 1'b1;
                        if (row_open && (addr[23:22] == open_bank) && (addr[21:9] == open_row)) begin
                            // Row hit: skip precharge+activate, go straight to read/write
                            sdram_a_int <= {4'b0000, addr[8:0]};
                            state <= wr ? ST_WRITE_CMD : ST_READ_CMD;
                        end else begin
                            // Always precharge before activate, even when
                            // row_open is false. The SDRAM needs an explicit
                            // precharge to reset its internal row latch.
                            state <= ST_PRECHARGE;
                        end
                    end
                end

                ST_REFRESH_WAIT: begin
                    if (wait_counter <= 3'd1) begin
                        state <= ST_IDLE;
                        ready <= 1'b1;
                    end else begin
                        wait_counter <= wait_counter - 3'd1;
                    end
                end

                ST_ACTIVATE: begin
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_ACTIVE;
                    sdram_ba     <= req_bank;
                    sdram_a_int[0]  <= req_addr[9];
                    sdram_a_int[1]  <= req_addr[10];
                    sdram_a_int[2]  <= req_addr[11];
                    sdram_a_int[3]  <= req_addr[12];
                    sdram_a_int[4]  <= req_addr[13];
                    sdram_a_int[5]  <= req_addr[14];
                    sdram_a_int[6]  <= req_addr[15];
                    sdram_a_int[7]  <= req_addr[16];
                    sdram_a_int[8]  <= req_addr[17];
                    sdram_a_int[9]  <= req_addr[18];
                    sdram_a_int[10] <= req_addr[19];
                    sdram_a_int[11] <= req_addr[20];
                    sdram_a_int[12] <= req_addr[21];
                    row_open     <= 1'b1;
                    open_bank    <= req_bank;
                    open_row     <= req_row;
                    state        <= ST_ACT_WAIT;
                    wait_counter <= T_RCD[2:0];
                end

                ST_ACT_WAIT: begin
                    if (wait_counter <= 3'd1) begin
                        sdram_a_int <= {4'b0000, req_col};
                        if (req_wr) begin
                            sdram_dq_out <= req_wdata;
                            sdram_dq_oe  <= 1'b1;
                        end
                        state <= req_wr ? ST_WRITE_CMD : ST_READ_CMD;
                    end else begin
                        wait_counter <= wait_counter - 3'd1;
                    end
                end

                ST_READ_CMD: begin
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_READ;
                    sdram_ba <= req_bank;
                    sdram_a_int  <= {4'b0000, req_col};
                    state        <= ST_READ_CAS;
                    wait_counter <= CAS_LATENCY[2:0];
                end

                ST_READ_CAS: begin
                    if (wait_counter <= 3'd1)
                        state <= ST_READ_CAPTURE;
                    else
                        wait_counter <= wait_counter - 3'd1;
                end

                ST_READ_CAPTURE: begin
                    rdata <= sdram_dq_in;
                    valid <= 1'b1;
                    state <= ST_IDLE;
                    ready <= 1'b1;
                end

                ST_WRITE_CMD: begin
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_WRITE;
                    sdram_ba     <= req_bank;
                    sdram_a_int  <= {4'b0000, req_col};
                    sdram_dq_out <= req_wdata;
                    sdram_dq_oe  <= 1'b1;
                    state        <= ST_WRITE_RECOVERY;
                    wait_counter <= T_WR[2:0];
                    dbg_last_write_a    <= {4'b0000, req_col};
                    dbg_last_write_ba   <= req_bank;
                    dbg_last_req_addr   <= req_addr;
                end

                ST_WRITE_RECOVERY: begin
                    if (wait_counter <= 3'd1) begin
                        state <= ST_IDLE;
                        ready <= 1'b1;
                    end
                    else
                        wait_counter <= wait_counter - 3'd1;
                end

                ST_PRECHARGE: begin
                    {sdram_csn, sdram_rasn, sdram_casn, sdram_wen} <= SCMD_PRECHARGE;
                    sdram_ba    <= req_bank;
                    sdram_a_int     <= 13'd0;
                    sdram_a_int[10] <= 1'b1;
                    row_open    <= 1'b0;
                    state        <= ST_PRECHARGE_WAIT;
                    wait_counter <= T_RP[2:0];
                end

                ST_PRECHARGE_WAIT: begin
                    if (wait_counter <= 3'd1) begin
                        sdram_a_int <= req_row;
                        fire_activate <= 1'b1;
                        state <= ST_ACTIVATE;
                    end else begin
                        wait_counter <= wait_counter - 3'd1;
                    end
                end

                default: state <= ST_INIT_WAIT;
            endcase

            sdram_a <= sdram_a_int;
        end
    end

    logic fire_activate;
endmodule
