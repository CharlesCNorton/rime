// trng: hardware true random number generator experiment.
// Prototype TRNG using ring oscillator jitter. Predecessor to the
// full EMBER image. See README.md.
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
    localparam integer CHANNELS = 8;
    localparam integer TAPS = 64;
    localparam integer ACCUM_ROUNDS = 10000000;

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
    wire tb = (tbc != 0);
    localparam integer UCC = ((CLK_HZ/BAUD)*11);
    always_ff @(posedge sys_clk) begin
        if (rst) tbc<=0; else if (tx_send) tbc<=UCC[15:0];
        else if (tbc!=0) tbc<=tbc-1;
    end

    (* keep *) wire rt0, rt1, rt2, rt3, rt4;
    (* keep *) LUT4 #(.INIT(16'h5555)) ro0(.Z(rt0),.A(rt4),.B(0),.C(0),.D(0));
    (* keep *) LUT4 #(.INIT(16'h5555)) ro1(.Z(rt1),.A(rt0),.B(0),.C(0),.D(0));
    (* keep *) LUT4 #(.INIT(16'h5555)) ro2(.Z(rt2),.A(rt1),.B(0),.C(0),.D(0));
    (* keep *) LUT4 #(.INIT(16'h5555)) ro3(.Z(rt3),.A(rt2),.B(0),.C(0),.D(0));
    (* keep *) LUT4 #(.INIT(16'h5555)) ro4(.Z(rt4),.A(rt3),.B(0),.C(0),.D(0));

    (* keep *) logic [7:0] meta;
    always_ff @(posedge sys_clk) begin
        meta <= {rt3,rt2,rt1,rt0, rt3,rt2,rt1,rt0};
    end

    logic [TAPS-1:0] cap [0:CHANNELS-1];
    genvar gch, gt;
    generate for (gch=0; gch<CHANNELS; gch=gch+1) begin : gch_blk
        wire [TAPS:0] dl;
        assign dl[0] = meta[gch];
        for (gt=0; gt<TAPS; gt=gt+1) begin : gt_blk
            (* keep *) LUT4 #(.INIT(16'hAAAA)) bl(.Z(dl[gt+1]),.A(dl[gt]),.B(0),.C(0),.D(0));
        end
        always_ff @(posedge sys_clk) begin
            for (int i=0; i<TAPS; i=i+1) cap[gch][i] <= dl[i+1];
        end
    end endgenerate

    logic [5:0] rbin [0:7];
    always_comb begin
        for (int c=0; c<8; c=c+1) begin
            rbin[c] = 6'd0;
            for (int tt=1; tt<TAPS; tt=tt+1)
                if (cap[c][tt] != cap[c][tt-1] && rbin[c]==6'd0)
                    rbin[c] = tt[5:0];
        end
    end

    (* ram_style = "block" *)
    reg [23:0] hist [0:511];
    logic [8:0]  hist_acc_addr, hist_out_addr;
    logic [23:0] hist_rdata;
    logic        hist_we;
    logic [23:0] hist_wdata;

    wire [8:0] hist_addr = accum ? hist_acc_addr : hist_out_addr;

    always_ff @(posedge sys_clk) begin
        hist_rdata <= hist[hist_addr];
        if (hist_we) hist[hist_addr] <= hist_wdata;
    end

    logic [31:0] rnd_cnt;
    logic accum;
    logic [2:0] uch;

    logic [1:0] accum_phase;
    logic [8:0] accum_addr;

    logic [31:0] sd_cnt;
    logic sd_rdy;
    always_ff @(posedge sys_clk) begin
        if (rst) begin sd_cnt<=0; sd_rdy<=0; end
        else if (!sd_rdy) begin
            if (sd_cnt[28]) sd_rdy<=1; else sd_cnt<=sd_cnt+1;
        end
    end

    always_ff @(posedge sys_clk) begin
        hist_we <= 0;
        if (rst) begin rnd_cnt<=0; accum<=0; uch<=0; accum_phase<=0; end
        else if (sd_rdy && !accum && rnd_cnt==0) begin accum<=1; accum_phase<=0; end
        else if (accum) begin
            case (accum_phase)
                2'd0: begin
                    accum_addr <= {uch, rbin[uch]};
                    hist_acc_addr <= {uch, rbin[uch]};
                    accum_phase <= 2'd1;
                end
                2'd1: begin
                    accum_phase <= 2'd2;
                end
                2'd2: begin
                    hist_acc_addr <= accum_addr;
                    hist_wdata <= hist_rdata + 24'd1;
                    hist_we    <= 1;
                    accum_phase <= 2'd0;
                    if (uch==3'd7) begin
                        uch<=0; rnd_cnt<=rnd_cnt+1;
                        if (rnd_cnt>=ACCUM_ROUNDS) accum<=0;
                    end else uch<=uch+1;
                end
                default: accum_phase <= 2'd0;
            endcase
        end
    end

    localparam [3:0] O_IDLE=0, O_HDR=1, O_LINE=2, O_HEX=3, O_NL=4, O_FTR=5, O_DONE=6, O_BRAM_WAIT=7, O_BRAM_RD=8;
    logic [3:0] os;
    logic [2:0] o_ch;
    logic [5:0] o_bin;
    logic [23:0] o_val;
    logic [3:0] hex_pos;
    logic [5:0] str_idx;

    function automatic [7:0] hex_char(input [3:0] n);
        hex_char = (n < 10) ? (8'd48 + {4'd0,n}) : (8'd65 + {4'd0,n} - 8'd10);
    endfunction

    function automatic [7:0] hdr_char(input [5:0] idx);
        case (idx)
            0: hdr_char=13;  1: hdr_char=10;
            2: hdr_char="M"; 3: hdr_char="E"; 4: hdr_char="T"; 5: hdr_char="A";
            6: hdr_char="S"; 7: hdr_char="T"; 8: hdr_char="A"; 9: hdr_char="B";
            10:hdr_char=" "; 11:hdr_char="T"; 12:hdr_char="A"; 13:hdr_char="U";
            14:hdr_char=" "; 15:hdr_char="E"; 16:hdr_char="C"; 17:hdr_char="P";
            18:hdr_char="5"; 19:hdr_char=13;  20:hdr_char=10;
            21:hdr_char="C"; 22:hdr_char="H"; 23:hdr_char=","; 24:hdr_char="B";
            25:hdr_char="I"; 26:hdr_char="N"; 27:hdr_char=","; 28:hdr_char="C";
            29:hdr_char="O"; 30:hdr_char="U"; 31:hdr_char="N"; 32:hdr_char="T";
            33:hdr_char=13;  34:hdr_char=10;
            default: hdr_char=0;
        endcase
    endfunction

    always_ff @(posedge sys_clk) begin
        tx_send <= 0;
        if (rst) begin os<=O_IDLE; o_ch<=0; o_bin<=0; str_idx<=0; end
        else case (os)
            O_IDLE: if (sd_rdy) begin str_idx<=0; os<=O_HDR; end

            O_HDR: if (!tb && !tx_send) begin
                if (str_idx < 6'd35) begin
                    tx_byte<=hdr_char(str_idx); tx_send<=1; str_idx<=str_idx+1;
                end else begin o_ch<=0; o_bin<=0; os<=O_LINE; end
            end

            O_LINE: begin
                hist_out_addr <= {o_ch, o_bin};
                hex_pos <= 4'd0;
                os <= 3'd7;
            end

            O_BRAM_WAIT: begin
                os <= O_BRAM_RD;
            end

            O_BRAM_RD: begin
                o_val <= hist_rdata;
                os <= O_HEX;
            end

            O_HEX: if (!tb && !tx_send) begin
                case (hex_pos)
                    4'd0: begin tx_byte<=hex_char({1'b0,o_ch}); tx_send<=1; hex_pos<=1; end
                    4'd1: begin tx_byte<=8'd44; tx_send<=1; hex_pos<=2; end
                    4'd2: begin tx_byte<=hex_char({2'b0,o_bin[5:4]}); tx_send<=1; hex_pos<=3; end
                    4'd3: begin tx_byte<=hex_char(o_bin[3:0]); tx_send<=1; hex_pos<=4; end
                    4'd4: begin tx_byte<=8'd44; tx_send<=1; hex_pos<=5; end
                    4'd5: begin tx_byte<=hex_char(o_val[23:20]); tx_send<=1; hex_pos<=6; end
                    4'd6: begin tx_byte<=hex_char(o_val[19:16]); tx_send<=1; hex_pos<=7; end
                    4'd7: begin tx_byte<=hex_char(o_val[15:12]); tx_send<=1; hex_pos<=8; end
                    4'd8: begin tx_byte<=hex_char(o_val[11:8]);  tx_send<=1; hex_pos<=9; end
                    4'd9: begin tx_byte<=hex_char(o_val[7:4]);   tx_send<=1; hex_pos<=10; end
                    4'd10: begin tx_byte<=hex_char(o_val[3:0]);  tx_send<=1; hex_pos<=11; end
                    4'd11: os <= O_NL;
                    default: os <= O_NL;
                endcase
            end

            O_NL: if (!tb && !tx_send) begin
                tx_byte<=8'd10; tx_send<=1;
                if (o_bin==6'd63) begin
                    if (o_ch==3'd7) begin str_idx<=0; os<=O_FTR; end
                    else begin o_ch<=o_ch+1; o_bin<=0; os<=O_LINE; end
                end else begin o_bin<=o_bin+1; os<=O_LINE; end
            end

            O_FTR: if (!tb && !tx_send) begin
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
    assign led = {hb[23], accum, sd_rdy, os==O_DONE, 1'b0};
endmodule
