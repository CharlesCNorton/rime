// ring-survey: die-level delay tomography experiment.
// Measures ring-oscillator frequency across spatial positions to
// map process variation. See README.md.
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

    localparam integer CLK_HZ = 12500000;
    localparam integer BAUD   = 115200;
    localparam integer NUM_SMALL_RINGS = 3000;
    localparam integer SMALL_RING_STAGES = 5;
    localparam integer LARGE_RING_STAGES = 1001;
    localparam integer MEAS_CYCLES = 125000;
    localparam integer RING_IDX_BITS = 12;

    logic [1:0] clk_div;
    wire sys_clk = clk_div[1];
    always_ff @(posedge clk) begin
        if (~button[0]) clk_div <= 2'd0;
        else clk_div <= clk_div + 2'd1;
    end

    logic [3:0] scc; logic scd;
    always_ff @(posedge sys_clk) begin
        if (~button[0]) begin scc<=0; scd<=0; end
        else if (!scd) begin if(scc==4'd15) scd<=1; else scc<=scc+1; end
    end
    wire rst = ~button[0] || !scd;

    logic tx_send; logic [7:0] tx_byte;
    uart_tx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) TX (.clk(sys_clk),.send(tx_send),.data(tx_byte),.tx(usb_tx));
    wire rx_v; wire [7:0] rx_d;
    uart_rx #(.CLK(CLK_HZ),.BAUD_RATE(BAUD)) RX (.clk(sys_clk),.rx(usb_rx),.finish(rx_v),.data(rx_d));
    logic [15:0] tbc;
    wire tbusy = (tbc != 0);
    localparam integer UCC = ((CLK_HZ/BAUD)*11);
    always_ff @(posedge sys_clk) begin
        if (rst) tbc<=0; else if (tx_send) tbc<=UCC[15:0];
        else if (tbc!=0) tbc<=tbc-1;
    end


    wire [NUM_SMALL_RINGS-1:0] small_ring_out;

    genvar sr;
    generate
        for (sr = 0; sr < NUM_SMALL_RINGS; sr = sr + 1) begin : gen_small
            (* keep *) wire [SMALL_RING_STAGES:0] r;
            assign r[0] = r[SMALL_RING_STAGES];
            genvar st;
            for (st = 0; st < SMALL_RING_STAGES; st = st + 1) begin : gen_st
                (* keep *) LUT4 #(.INIT(16'h5555)) inv (
                    .Z(r[st+1]), .A(r[st]), .B(1'b0), .C(1'b0), .D(1'b0)
                );
            end
            assign small_ring_out[sr] = r[1];
        end
    endgenerate

    (* keep *) wire [LARGE_RING_STAGES:0] lr;
    assign lr[0] = lr[LARGE_RING_STAGES];
    genvar li;
    generate
        for (li = 0; li < LARGE_RING_STAGES; li = li + 1) begin : gen_large
            (* keep *) LUT4 #(.INIT(16'h5555)) linv (
                .Z(lr[li+1]), .A(lr[li]), .B(1'b0), .C(1'b0), .D(1'b0)
            );
        end
    endgenerate
    wire large_ring_out = lr[1];


    logic [RING_IDX_BITS-1:0] meas_idx;
    logic mux_out;

    always_comb begin
        if (meas_idx == NUM_SMALL_RINGS[RING_IDX_BITS-1:0])
            mux_out = large_ring_out;
        else if (meas_idx < NUM_SMALL_RINGS[RING_IDX_BITS-1:0])
            mux_out = small_ring_out[meas_idx];
        else
            mux_out = 1'b0;
    end

    logic sync0, sync1, sync2;
    wire meas_edge = sync1 && !sync2;
    always_ff @(posedge sys_clk) begin
        if (rst) begin sync0<=0; sync1<=0; sync2<=0; end
        else begin sync0<=mux_out; sync1<=sync0; sync2<=sync1; end
    end

    logic [21:0] edge_count;
    logic [16:0] meas_timer;

    (* ram_style = "block" *)
    reg [21:0] results [0:4095];
    logic [RING_IDX_BITS-1:0] bram_wr_addr;
    logic [RING_IDX_BITS-1:0] bram_rd_addr;
    logic [21:0] bram_rd_data;
    logic bram_we;

    always_ff @(posedge sys_clk) begin
        bram_rd_data <= results[bram_rd_addr];
        if (bram_we) results[bram_wr_addr] <= edge_count;
    end

    logic [31:0] sd_cnt;
    logic sd_rdy;
    always_ff @(posedge sys_clk) begin
        if (rst) begin sd_cnt<=0; sd_rdy<=0; end
        else if (!sd_rdy) begin
            if (sd_cnt[28]) sd_rdy<=1; else sd_cnt<=sd_cnt+1;
        end
    end

    localparam [2:0] M_IDLE=0, M_SETTLE=1, M_COUNT=2, M_STORE=3, M_DONE=4;
    logic [2:0] ms;
    logic [7:0] settle_cnt;

    always_ff @(posedge sys_clk) begin
        bram_we <= 0;
        if (rst) begin
            ms <= M_IDLE; meas_idx <= 0; edge_count <= 0; meas_timer <= 0;
        end else case (ms)
            M_IDLE: if (sd_rdy) begin
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
                if (meas_edge) edge_count <= edge_count + 22'd1;
                meas_timer <= meas_timer + 17'd1;
                if (meas_timer >= MEAS_CYCLES[16:0]) begin
                    ms <= M_STORE;
                end
            end

            M_STORE: begin
                bram_wr_addr <= meas_idx;
                bram_we <= 1;
                if (meas_idx == NUM_SMALL_RINGS[RING_IDX_BITS-1:0]) begin
                    ms <= M_DONE;
                end else begin
                    meas_idx <= meas_idx + 1;
                    settle_cnt <= 0;
                    ms <= M_SETTLE;
                end
            end

            M_DONE: ;
        endcase
    end

    localparam [3:0] O_IDLE=0, O_HDR=1, O_STATS=2, O_RD=3, O_RD_WAIT=4,
                     O_LINE=5, O_NL=6, O_FTR=7, O_DONE=8;
    logic [3:0] os;
    logic [RING_IDX_BITS-1:0] o_idx;
    logic [21:0] o_val;
    logic [3:0] hex_pos;
    logic [5:0] str_idx;

    function automatic [7:0] hex_char(input [3:0] n);
        hex_char = (n<10) ? (8'd48+{4'd0,n}) : (8'd65+{4'd0,n}-8'd10);
    endfunction

    function automatic [7:0] hdr_char(input [5:0] idx);
        case (idx)
            0:hdr_char=13; 1:hdr_char=10;
            2:hdr_char="R"; 3:hdr_char="I"; 4:hdr_char="N"; 5:hdr_char="G";
            6:hdr_char=" "; 7:hdr_char="S"; 8:hdr_char="U"; 9:hdr_char="R";
            10:hdr_char="V"; 11:hdr_char="E"; 12:hdr_char="Y"; 13:hdr_char=" ";
            14:hdr_char="E"; 15:hdr_char="C"; 16:hdr_char="P"; 17:hdr_char="5";
            18:hdr_char=13; 19:hdr_char=10;
            default: hdr_char=0;
        endcase
    endfunction

    always_ff @(posedge sys_clk) begin
        tx_send <= 0;
        if (rst) begin os<=O_IDLE; o_idx<=0; str_idx<=0; end
        else case (os)
            O_IDLE: if (ms == M_DONE) begin str_idx<=0; os<=O_HDR; end

            O_HDR: if (!tbusy && !tx_send) begin
                if (str_idx < 6'd20) begin
                    tx_byte<=hdr_char(str_idx); tx_send<=1; str_idx<=str_idx+1;
                end else begin o_idx<=0; os<=O_RD; end
            end

            O_RD: begin
                bram_rd_addr <= o_idx;
                os <= O_RD_WAIT;
            end

            O_RD_WAIT: begin
                o_val <= bram_rd_data;
                hex_pos <= 0;
                str_idx <= 0;
                os <= O_LINE;
            end

            O_LINE: if (!tbusy && !tx_send) begin
                if (o_idx == NUM_SMALL_RINGS[RING_IDX_BITS-1:0]) begin
                    case (str_idx)
                        0: begin tx_byte<="L"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=7; end
                        7: begin tx_byte<=hex_char({2'b0, o_val[21:20]}); tx_send<=1; str_idx<=8; end
                        8: begin tx_byte<=hex_char(o_val[19:16]); tx_send<=1; str_idx<=9; end
                        9: begin tx_byte<=hex_char(o_val[15:12]); tx_send<=1; str_idx<=10; end
                        10:begin tx_byte<=hex_char(o_val[11:8]);  tx_send<=1; str_idx<=11; end
                        11:begin tx_byte<=hex_char(o_val[7:4]);   tx_send<=1; str_idx<=12; end
                        12:begin tx_byte<=hex_char(o_val[3:0]);   tx_send<=1; str_idx<=13; end
                        13: os<=O_NL;
                        default: str_idx<=13;
                    endcase
                end else begin
                    case (str_idx)
                        0: begin tx_byte<="R"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                        2: begin tx_byte<=hex_char(o_idx[11:8]); tx_send<=1; str_idx<=3; end
                        3: begin tx_byte<=hex_char(o_idx[7:4]);  tx_send<=1; str_idx<=4; end
                        4: begin tx_byte<=hex_char(o_idx[3:0]);  tx_send<=1; str_idx<=5; end
                        5: begin tx_byte<=","; tx_send<=1; str_idx<=6; end
                        6: begin tx_byte<=hex_char({2'b0, o_val[21:20]}); tx_send<=1; str_idx<=7; end
                        7: begin tx_byte<=hex_char(o_val[19:16]); tx_send<=1; str_idx<=8; end
                        8: begin tx_byte<=hex_char(o_val[15:12]); tx_send<=1; str_idx<=9; end
                        9: begin tx_byte<=hex_char(o_val[11:8]);  tx_send<=1; str_idx<=10; end
                        10:begin tx_byte<=hex_char(o_val[7:4]);   tx_send<=1; str_idx<=11; end
                        11:begin tx_byte<=hex_char(o_val[3:0]);   tx_send<=1; str_idx<=12; end
                        12: os<=O_NL;
                        default: str_idx<=12;
                    endcase
                end
            end

            O_NL: if (!tbusy && !tx_send) begin
                tx_byte<=10; tx_send<=1;
                if (o_idx == NUM_SMALL_RINGS[RING_IDX_BITS-1:0]) begin
                    str_idx<=0; os<=O_FTR;
                end else begin
                    o_idx<=o_idx+1; os<=O_RD;
                end
            end

            O_FTR: if (!tbusy && !tx_send) begin
                case (str_idx)
                    0: begin tx_byte<="D"; tx_send<=1; str_idx<=1; end
                    1: begin tx_byte<="O"; tx_send<=1; str_idx<=2; end
                    2: begin tx_byte<="N"; tx_send<=1; str_idx<=3; end
                    3: begin tx_byte<="E"; tx_send<=1; str_idx<=4; end
                    4: begin tx_byte<=10;  tx_send<=1; str_idx<=5; end
                    default: os<=O_DONE;
                endcase
            end

            O_DONE: ;
        endcase
    end

    logic [23:0] hb;
    always_ff @(posedge sys_clk) begin if(rst) hb<=0; else hb<=hb+1; end
    assign led = {hb[23], ms!=M_DONE && ms!=M_IDLE, meas_idx[11:10], sd_rdy};
endmodule
