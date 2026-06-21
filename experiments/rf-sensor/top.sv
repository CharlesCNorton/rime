// rf-sensor: electromagnetic sensitivity grid experiment.
// Maps RF pickup across the die using ring-oscillator frequency
// perturbation under external RF stimulus. See README.md.
module top (
    input  wire       clk,
    input  wire       usb_rx,
    output wire       usb_tx,
    output logic [4:0] led,
    input  wire [1:0] button,
    output wire flash_csn, output wire flash_mosi,
    output wire flash_wpn, output wire flash_resetn,
    input  wire flash_miso,
    output wire sd_clk, output wire sd_csn, output wire sd_mosi,
    input  wire sd_miso, input wire sd_det,
    output wire sdram_clk, output wire sdram_cke, output wire sdram_csn,
    output wire sdram_rasn, output wire sdram_casn, output wire sdram_wen,
    output wire [1:0] sdram_ba, output wire [12:0] sdram_a,
    inout  wire [15:0] sdram_dq, output wire [1:0] sdram_dqm
);
    assign flash_csn=1; assign flash_mosi=0; assign flash_wpn=1; assign flash_resetn=1;
    assign sd_clk=0; assign sd_csn=1; assign sd_mosi=1;
    assign sdram_clk=0; assign sdram_cke=0; assign sdram_csn=1;
    assign sdram_rasn=1; assign sdram_casn=1; assign sdram_wen=1;
    assign sdram_ba=0; assign sdram_a=0; assign sdram_dqm=2'b11;
    assign sdram_dq=16'bz;

    localparam integer CLK_HZ      = 12500000;
    localparam integer BAUD        = 115200;
    localparam integer NUM_RINGS   = 256;
    localparam integer GRID_W      = 16;
    localparam integer GRID_H      = 16;
    localparam integer RING_STAGES = 5;
    localparam integer MEAS_CYCLES = 12500;
    localparam integer IDX_BITS    = 9;

    logic [1:0] clk_div;
    wire sys_clk = clk_div[1];
    always_ff @(posedge clk) begin
        if (~button[0]) clk_div <= 0; else clk_div <= clk_div + 1;
    end
    logic [3:0] scc; logic scd;
    always_ff @(posedge sys_clk) begin
        if (~button[0]) begin scc<=0; scd<=0; end
        else if (!scd) begin if (scc==15) scd<=1; else scc<=scc+1; end
    end
    wire rst = ~button[0] || !scd;

    logic tx_send; logic [7:0] tx_byte;
    uart_tx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) TX (
        .clk(sys_clk),.send(tx_send),.data(tx_byte),.tx(usb_tx)
    );
    wire rx_v; wire [7:0] rx_d;
    uart_rx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) RX (
        .clk(sys_clk),.rx(usb_rx),.finish(rx_v),.data(rx_d)
    );
    logic [15:0] tbc;
    wire tbusy = (tbc != 0);
    localparam integer UCC = ((CLK_HZ/BAUD)*11);
    always_ff @(posedge sys_clk) begin
        if (rst) tbc<=0; else if (tx_send) tbc<=UCC[15:0];
        else if (tbc!=0) tbc<=tbc-1;
    end


    wire [NUM_RINGS-1:0] ring_out;
    genvar ri;
    generate for (ri = 0; ri < NUM_RINGS; ri = ri + 1) begin : gen_ring
        (* keep *) wire [RING_STAGES:0] r;
        assign r[0] = r[RING_STAGES];
        genvar st;
        for (st = 0; st < RING_STAGES; st = st + 1) begin : gen_st
            (* keep *) LUT4 #(.INIT(16'h5555)) inv(
                .Z(r[st+1]), .A(r[st]), .B(1'b0), .C(1'b0), .D(1'b0)
            );
        end
        assign ring_out[ri] = r[1];
    end endgenerate


    logic [IDX_BITS-1:0] meas_idx;
    logic mux_out;

    always_comb begin
        if (meas_idx < NUM_RINGS[IDX_BITS-1:0])
            mux_out = ring_out[meas_idx];
        else
            mux_out = 1'b0;
    end

    logic sync0, sync1, sync2;
    wire meas_edge = sync1 && !sync2;
    always_ff @(posedge sys_clk) begin
        if (rst) begin sync0<=0; sync1<=0; sync2<=0; end
        else begin sync0<=mux_out; sync1<=sync0; sync2<=sync1; end
    end

    logic [19:0] edge_count;
    logic [13:0] meas_timer;

    (* ram_style = "block" *)
    reg [19:0] results [0:255];
    logic [IDX_BITS-1:0] bram_wr_addr, bram_rd_addr;
    logic [19:0] bram_rd_data;
    logic bram_we;

    always_ff @(posedge sys_clk) begin
        bram_rd_data <= results[bram_rd_addr];
        if (bram_we) results[bram_wr_addr] <= edge_count;
    end

    logic [15:0] sweep_count;

    logic [31:0] sd_cnt; logic sd_rdy;
    always_ff @(posedge sys_clk) begin
        if (rst) begin sd_cnt<=0; sd_rdy<=0; end
        else if (!sd_rdy) begin
            if (sd_cnt >= CLK_HZ * 5) sd_rdy<=1;
            else sd_cnt<=sd_cnt+1;
        end
    end

    logic ref_s0, ref_s1, ref_s2;
    wire ref_edge = ref_s1 && !ref_s2;
    always_ff @(posedge sys_clk) begin
        if (rst) begin ref_s0<=0; ref_s1<=0; ref_s2<=0; end
        else begin ref_s0<=ring_out[0]; ref_s1<=ref_s0; ref_s2<=ref_s1; end
    end
    logic [31:0] ref_count, ref_timer, ref_freq;
    always_ff @(posedge sys_clk) begin
        if (rst) begin ref_count<=0; ref_timer<=0; ref_freq<=0; end
        else begin
            if (ref_edge) ref_count <= ref_count + 1;
            ref_timer <= ref_timer + 1;
            if (ref_timer >= CLK_HZ) begin
                ref_freq <= ref_count;
                ref_count <= 0;
                ref_timer <= 0;
            end
        end
    end

    localparam [2:0] M_IDLE=0, M_SETTLE=1, M_COUNT=2, M_STORE=3, M_OUTPUT=4;
    logic [2:0] ms;
    logic [7:0] settle_cnt;

    always_ff @(posedge sys_clk) begin
        bram_we <= 0;
        if (rst) begin
            ms<=M_IDLE; meas_idx<=0; edge_count<=0; meas_timer<=0;
            sweep_count<=0;
        end else case (ms)
            M_IDLE: if (sd_rdy && os == O_MAIN) begin
                meas_idx <= 0;
                settle_cnt <= 0;
                ms <= M_SETTLE;
            end

            M_SETTLE: begin
                if (settle_cnt >= 8'd8) begin
                    edge_count <= 0;
                    meas_timer <= 0;
                    ms <= M_COUNT;
                end else settle_cnt <= settle_cnt + 8'd1;
            end

            M_COUNT: begin
                if (meas_edge) edge_count <= edge_count + 20'd1;
                meas_timer <= meas_timer + 14'd1;
                if (meas_timer >= MEAS_CYCLES[13:0]) ms <= M_STORE;
            end

            M_STORE: begin
                bram_wr_addr <= meas_idx;
                bram_we <= 1;
                if (meas_idx == NUM_RINGS[IDX_BITS-1:0] - 8'd1) begin
                    ms <= M_OUTPUT;
                end else begin
                    meas_idx <= meas_idx + 1;
                    settle_cnt <= 0;
                    ms <= M_SETTLE;
                end
            end

            M_OUTPUT: begin
                if (output_sweep_done) begin
                    sweep_count <= sweep_count + 1;
                    meas_idx <= 0;
                    settle_cnt <= 0;
                    ms <= M_SETTLE;
                end
            end
        endcase
    end

    localparam [3:0] O_IDLE=0, O_HDR=1, O_CFG=2, O_MAIN=3,
                     O_RD=4, O_RDW=5, O_LINE=6, O_NL=7,
                     O_SWEEP_END=8, O_SE_HEX=9, O_SE_NL=10;
    logic [3:0] os;
    logic [IDX_BITS-1:0] o_idx;
    logic [19:0] o_val20;
    logic [31:0] o_val32;
    logic [3:0] hex_pos;
    logic [5:0] str_idx;
    logic output_sweep_done;

    function automatic [7:0] hex_char(input [3:0] n);
        hex_char = (n < 10) ? (8'd48 + {4'd0, n}) : (8'd65 + {4'd0, n} - 8'd10);
    endfunction

    function automatic [7:0] hdr_char(input [5:0] idx);
        case (idx)
            0:hdr_char=13; 1:hdr_char=10;
            2:hdr_char="R"; 3:hdr_char="F"; 4:hdr_char=" ";
            5:hdr_char="S"; 6:hdr_char="E"; 7:hdr_char="N";
            8:hdr_char="S"; 9:hdr_char="O"; 10:hdr_char="R";
            11:hdr_char=" "; 12:hdr_char="E"; 13:hdr_char="C";
            14:hdr_char="P"; 15:hdr_char="5";
            16:hdr_char=13; 17:hdr_char=10;
            default: hdr_char=0;
        endcase
    endfunction

    always_ff @(posedge sys_clk) begin
        tx_send <= 0;
        output_sweep_done <= 0;
        if (rst) begin os<=O_IDLE; o_idx<=0; str_idx<=0; end
        else case (os)
            O_IDLE: if (sd_rdy) begin str_idx<=0; os<=O_HDR; end

            O_HDR: if (!tbusy && !tx_send) begin
                if (str_idx < 6'd18) begin
                    tx_byte <= hdr_char(str_idx);
                    tx_send <= 1;
                    str_idx <= str_idx + 1;
                end else begin str_idx <= 0; os <= O_CFG; end
            end

            O_CFG: if (!tbusy && !tx_send) begin
                case (str_idx)
                    0: begin tx_byte<="G"; tx_send<=1; str_idx<=1; end
                    1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                    2: begin tx_byte<="1"; tx_send<=1; str_idx<=3; end
                    3: begin tx_byte<="0"; tx_send<=1; str_idx<=4; end
                    4: begin tx_byte<=","; tx_send<=1; str_idx<=5; end
                    5: begin tx_byte<="1"; tx_send<=1; str_idx<=6; end
                    6: begin tx_byte<="0"; tx_send<=1; str_idx<=7; end
                    7: begin tx_byte<=","; tx_send<=1; str_idx<=8; end
                    8: begin tx_byte<="0"; tx_send<=1; str_idx<=9; end
                    9: begin tx_byte<="1"; tx_send<=1; str_idx<=10; end
                    10:begin tx_byte<=","; tx_send<=1; str_idx<=11; end
                    11:begin tx_byte<="0"; tx_send<=1; str_idx<=12; end
                    12:begin tx_byte<="1"; tx_send<=1; str_idx<=13; end
                    13:begin tx_byte<="0"; tx_send<=1; str_idx<=14; end
                    14:begin tx_byte<="0"; tx_send<=1; str_idx<=15; end
                    15:begin tx_byte<=10;  tx_send<=1; os<=O_MAIN; end
                    default: str_idx<=15;
                endcase
            end

            O_MAIN: begin
                if (ms == M_OUTPUT) begin
                    o_idx <= 0;
                    os <= O_RD;
                end
            end

            O_RD: begin
                bram_rd_addr <= o_idx;
                os <= O_RDW;
            end

            O_RDW: begin
                o_val20 <= bram_rd_data;
                str_idx <= 0;
                os <= O_LINE;
            end

            O_LINE: if (!tbusy && !tx_send) begin
                case (str_idx)
                    0: begin tx_byte<="R"; tx_send<=1; str_idx<=1; end
                    1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                    2: begin tx_byte<=hex_char(sweep_count[15:12]); tx_send<=1; str_idx<=3; end
                    3: begin tx_byte<=hex_char(sweep_count[11:8]);  tx_send<=1; str_idx<=4; end
                    4: begin tx_byte<=hex_char(sweep_count[7:4]);   tx_send<=1; str_idx<=5; end
                    5: begin tx_byte<=hex_char(sweep_count[3:0]);   tx_send<=1; str_idx<=6; end
                    6: begin tx_byte<=","; tx_send<=1; str_idx<=7; end
                    7: begin tx_byte<=hex_char({4'd0, o_idx[7:4]}); tx_send<=1; str_idx<=8; end
                    8: begin tx_byte<=hex_char(o_idx[3:0]); tx_send<=1; str_idx<=9; end
                    9: begin tx_byte<=","; tx_send<=1; str_idx<=10; end
                    10:begin tx_byte<=hex_char(o_val20[19:16]); tx_send<=1; str_idx<=11; end
                    11:begin tx_byte<=hex_char(o_val20[15:12]); tx_send<=1; str_idx<=12; end
                    12:begin tx_byte<=hex_char(o_val20[11:8]);  tx_send<=1; str_idx<=13; end
                    13:begin tx_byte<=hex_char(o_val20[7:4]);   tx_send<=1; str_idx<=14; end
                    14:begin tx_byte<=hex_char(o_val20[3:0]);   tx_send<=1; str_idx<=15; end
                    15: os <= O_NL;
                    default: str_idx <= 15;
                endcase
            end

            O_NL: if (!tbusy && !tx_send) begin
                tx_byte <= 10; tx_send <= 1;
                if (o_idx == NUM_RINGS[IDX_BITS-1:0] - 8'd1) begin
                    str_idx <= 0;
                    os <= O_SWEEP_END;
                end else begin
                    o_idx <= o_idx + 1;
                    os <= O_RD;
                end
            end

            O_SWEEP_END: if (!tbusy && !tx_send) begin
                case (str_idx)
                    0: begin tx_byte<="T"; tx_send<=1; str_idx<=1; end
                    1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                    2: begin tx_byte<=hex_char(sweep_count[15:12]); tx_send<=1; str_idx<=3; end
                    3: begin tx_byte<=hex_char(sweep_count[11:8]);  tx_send<=1; str_idx<=4; end
                    4: begin tx_byte<=hex_char(sweep_count[7:4]);   tx_send<=1; str_idx<=5; end
                    5: begin tx_byte<=hex_char(sweep_count[3:0]);   tx_send<=1; str_idx<=6; end
                    6: begin tx_byte<=","; tx_send<=1; str_idx<=7; end
                    7: begin o_val32<=ref_freq; hex_pos<=0; str_idx<=8; end
                    8: begin
                        if (hex_pos < 8) begin
                            tx_byte <= hex_char(o_val32[31 - hex_pos*4 -: 4]);
                            tx_send <= 1; hex_pos <= hex_pos + 1;
                        end else os <= O_SE_NL;
                    end
                    default: str_idx <= 8;
                endcase
            end

            O_SE_NL: if (!tbusy && !tx_send) begin
                tx_byte <= 10; tx_send <= 1;
                output_sweep_done <= 1;
                os <= O_MAIN;
            end

            default: os <= O_IDLE;
        endcase
    end

    logic [23:0] hb;
    always_ff @(posedge sys_clk) begin if (rst) hb<=0; else hb<=hb+1; end
    assign led = {hb[23], ms!=M_IDLE, meas_idx[7:6], sd_rdy};
endmodule
