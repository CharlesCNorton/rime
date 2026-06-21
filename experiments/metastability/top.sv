// metastability: setup/hold time characterization on ECP5 fabric.
// Measures the metastability time constant (tau) of flip-flops
// under deliberate setup-time violation. See README.md.
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

    localparam integer CLK_HZ = 13333333;
    localparam integer BAUD   = 115200;
    localparam integer CHAINS = 4;
    localparam integer STAGES = 8;
    localparam integer PAIRS  = STAGES - 1;
    localparam integer RING_STAGES = 127;
    localparam [39:0] ACCUM_TARGET = 40'd20_000_000_000;
    localparam [31:0] FREQ_INTERVAL = 32'd133333330;
    localparam integer MAX_FREQ_SNAPSHOTS = 150;

    wire sys_clk;
    wire pll_lock;

    (* FREQUENCY_PIN_CLKI="50" *)
    (* FREQUENCY_PIN_CLKOP="13.3333" *)
    (* ICP_CURRENT="12" *)
    (* LPF_RESISTOR="8" *)
    (* MFG_ENABLE_FILTEROPAMP="1" *)
    (* MFG_GMCREF_SEL="2" *)
    EHXPLLL #(
        .PLLRST_ENA("DISABLED"),
        .INTFB_WAKE("DISABLED"),
        .STDBY_ENABLE("DISABLED"),
        .DPHASE_SOURCE("DISABLED"),
        .OUTDIVIDER_MUXA("DIVA"),
        .OUTDIVIDER_MUXB("DIVB"),
        .OUTDIVIDER_MUXC("DIVC"),
        .OUTDIVIDER_MUXD("DIVD"),
        .CLKI_DIV(15),
        .CLKOP_ENABLE("ENABLED"),
        .CLKOP_DIV(44),
        .CLKOP_CPHASE(22),
        .CLKOP_FPHASE(0),
        .FEEDBK_PATH("CLKOP"),
        .CLKFB_DIV(4)
    ) pll_inst (
        .RST(1'b0),
        .STDBY(1'b0),
        .CLKI(clk),
        .CLKOP(sys_clk),
        .CLKFB(sys_clk),
        .CLKINTFB(),
        .PHASESEL0(1'b0),
        .PHASESEL1(1'b0),
        .PHASEDIR(1'b1),
        .PHASESTEP(1'b1),
        .PHASELOADREG(1'b1),
        .PLLWAKESYNC(1'b0),
        .ENCLKOP(1'b0),
        .LOCK(pll_lock)
    );

    logic [3:0] scc; logic scd;
    always_ff @(posedge sys_clk) begin
        if (~button[0] || !pll_lock) begin scc<=0; scd<=0; end
        else if (!scd) begin if(scc==4'd15) scd<=1; else scc<=scc+1; end
    end
    wire rst = ~button[0] || !scd || !pll_lock;

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

    (* keep *) wire [RING_STAGES:0] ring;
    assign ring[0] = ring[RING_STAGES];
    genvar ri;
    generate
        for (ri = 0; ri < RING_STAGES; ri = ri + 1) begin : gen_ring
            (* keep *) LUT4 #(.INIT(16'h5555)) rinv (
                .Z(ring[ri+1]), .A(ring[ri]), .B(1'b0), .C(1'b0), .D(1'b0)
            );
        end
    endgenerate

    logic ring_sync0, ring_sync1, ring_sync2;
    always_ff @(posedge sys_clk) begin
        if (rst) begin ring_sync0<=0; ring_sync1<=0; ring_sync2<=0; end
        else begin
            ring_sync0 <= ring[1];
            ring_sync1 <= ring_sync0;
            ring_sync2 <= ring_sync1;
        end
    end
    wire ring_edge = ring_sync1 && !ring_sync2;

    logic [31:0] ring_count;
    logic [31:0] freq_timer;
    logic [7:0]  freq_snap_idx;

    (* ram_style = "block" *)
    reg [31:0] freq_snaps [0:MAX_FREQ_SNAPSHOTS-1];
    logic        freq_done;

    always_ff @(posedge sys_clk) begin
        if (rst) begin
            ring_count <= 0;
            freq_timer <= 0;
            freq_snap_idx <= 0;
            freq_done <= 0;
        end else if (accum && !freq_done) begin
            if (ring_edge) ring_count <= ring_count + 1;
            freq_timer <= freq_timer + 1;
            if (freq_timer >= FREQ_INTERVAL) begin
                freq_snaps[freq_snap_idx] <= ring_count;
                ring_count <= 0;
                freq_timer <= 0;
                if (freq_snap_idx >= MAX_FREQ_SNAPSHOTS - 1)
                    freq_done <= 1;
                else
                    freq_snap_idx <= freq_snap_idx + 1;
            end
        end
    end

    (* keep *) logic [STAGES-1:0] sync [0:CHAINS-1];
    always_ff @(posedge sys_clk) begin
        if (rst) begin
            for (int c = 0; c < CHAINS; c = c + 1) sync[c] <= 0;
        end else begin
            sync[0][0] <= ring[1];
            sync[1][0] <= ring[32];
            sync[2][0] <= ring[64];
            sync[3][0] <= ring[96];
            for (int c = 0; c < CHAINS; c = c + 1)
                for (int s = 1; s < STAGES; s = s + 1)
                    sync[c][s] <= sync[c][s-1];
        end
    end

    (* keep *) logic [STAGES-1:0] sync_prev [0:CHAINS-1];
    always_ff @(posedge sys_clk) begin
        if (rst) begin
            for (int c = 0; c < CHAINS; c = c + 1) sync_prev[c] <= 0;
        end else begin
            for (int c = 0; c < CHAINS; c = c + 1) sync_prev[c] <= sync[c];
        end
    end

    logic [39:0] fail_count [0:CHAINS-1][0:PAIRS-1];
    logic [39:0] sample_count;
    logic        accum;

    logic [31:0] sd_cnt;
    logic sd_rdy;
    always_ff @(posedge sys_clk) begin
        if (rst) begin sd_cnt<=0; sd_rdy<=0; end
        else if (!sd_rdy) begin
            if (sd_cnt[28]) sd_rdy<=1; else sd_cnt<=sd_cnt+1;
        end
    end

    always_ff @(posedge sys_clk) begin
        if (rst) begin
            accum<=0; sample_count<=0;
            for (int c=0; c<CHAINS; c=c+1)
                for (int p=0; p<PAIRS; p=p+1)
                    fail_count[c][p] <= 0;
        end else if (sd_rdy && !accum && sample_count==0) begin
            accum <= 1;
        end else if (accum) begin
            sample_count <= sample_count + 1;
            for (int c=0; c<CHAINS; c=c+1)
                for (int p=0; p<PAIRS; p=p+1)
                    if (sync[c][p+1] != sync_prev[c][p])
                        fail_count[c][p] <= fail_count[c][p] + 1;
            if (sample_count >= ACCUM_TARGET) accum <= 0;
        end
    end

    localparam [3:0] O_IDLE=0, O_HDR=1, O_SAMP=2, O_SH=3,
                     O_LINE=4, O_HEX=5, O_NL=6, O_FTR=7, O_DONE=8,
                     O_FREQ=9, O_FH=10;
    logic [3:0] os;
    logic [1:0] o_ch;
    logic [2:0] o_pair;
    logic [39:0] o_val40;
    logic [31:0] o_val32;
    logic [3:0] hex_pos;
    logic [5:0] str_idx;
    logic [2:0] stats_field;
    logic [7:0] freq_out_idx;

    function automatic [7:0] hex_char(input [3:0] n);
        hex_char = (n<10) ? (8'd48+{4'd0,n}) : (8'd65+{4'd0,n}-8'd10);
    endfunction

    function automatic [7:0] hdr_char(input [5:0] idx);
        case (idx)
            0:hdr_char=13; 1:hdr_char=10;
            2:hdr_char="M"; 3:hdr_char="T"; 4:hdr_char="B"; 5:hdr_char="F";
            6:hdr_char=" "; 7:hdr_char="D"; 8:hdr_char="E"; 9:hdr_char="E";
            10:hdr_char="P"; 11:hdr_char=" "; 12:hdr_char="E"; 13:hdr_char="C";
            14:hdr_char="P"; 15:hdr_char="5"; 16:hdr_char=13; 17:hdr_char=10;
            default: hdr_char=0;
        endcase
    endfunction

    always_ff @(posedge sys_clk) begin
        tx_send<=0;
        if (rst) begin os<=O_IDLE; o_ch<=0; o_pair<=0; str_idx<=0; freq_out_idx<=0; end
        else case (os)
            O_IDLE: if (sd_rdy && !accum && sample_count>0) begin str_idx<=0; os<=O_HDR; end

            O_HDR: if (!tbusy && !tx_send) begin
                if (str_idx<6'd18) begin
                    tx_byte<=hdr_char(str_idx); tx_send<=1; str_idx<=str_idx+1;
                end else begin o_val40<=sample_count; hex_pos<=0; str_idx<=0; os<=O_SAMP; end
            end

            O_SAMP: if (!tbusy && !tx_send) begin
                case (str_idx)
                    0: begin tx_byte<="S"; tx_send<=1; str_idx<=1; end
                    1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                    2: begin hex_pos<=0; stats_field<=0; os<=O_SH; end
                    default: str_idx<=0;
                endcase
            end

            O_SH: if (!tbusy && !tx_send) begin
                if (hex_pos<4'd10) begin
                    tx_byte<=hex_char(o_val40[39-hex_pos*4-:4]); tx_send<=1; hex_pos<=hex_pos+1;
                end else begin
                    tx_byte<=10; tx_send<=1;
                    o_ch<=0; o_pair<=0; str_idx<=0; os<=O_LINE;
                end
            end

            O_LINE: if (!tbusy && !tx_send) begin
                case (str_idx)
                    0: begin tx_byte<="C"; tx_send<=1; str_idx<=1; end
                    1: begin tx_byte<=8'd48+{6'd0,o_ch}; tx_send<=1; str_idx<=2; end
                    2: begin tx_byte<=","; tx_send<=1; str_idx<=3; end
                    3: begin tx_byte<="P"; tx_send<=1; str_idx<=4; end
                    4: begin tx_byte<=8'd48+{5'd0,o_pair}; tx_send<=1; str_idx<=5; end
                    5: begin tx_byte<=","; tx_send<=1; str_idx<=6; end
                    6: begin o_val40<=fail_count[o_ch][o_pair]; hex_pos<=0; os<=O_HEX; end
                    default: str_idx<=0;
                endcase
            end

            O_HEX: if (!tbusy && !tx_send) begin
                if (hex_pos<4'd10) begin
                    tx_byte<=hex_char(o_val40[39-hex_pos*4-:4]); tx_send<=1; hex_pos<=hex_pos+1;
                end else os<=O_NL;
            end

            O_NL: if (!tbusy && !tx_send) begin
                tx_byte<=10; tx_send<=1; str_idx<=0;
                if (o_pair==3'd6) begin
                    if (o_ch==2'd3) begin freq_out_idx<=0; os<=O_FREQ; end
                    else begin o_ch<=o_ch+1; o_pair<=0; os<=O_LINE; end
                end else begin o_pair<=o_pair+1; os<=O_LINE; end
            end

            O_FREQ: if (!tbusy && !tx_send) begin
                if (freq_out_idx > freq_snap_idx) begin
                    str_idx<=0; os<=O_FTR;
                end else begin
                    case (str_idx)
                        0: begin tx_byte<="F"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                        2: begin tx_byte<=hex_char(freq_out_idx[7:4]); tx_send<=1; str_idx<=3; end
                        3: begin tx_byte<=hex_char(freq_out_idx[3:0]); tx_send<=1; str_idx<=4; end
                        4: begin tx_byte<=","; tx_send<=1; str_idx<=5; end
                        5: begin hex_pos<=0; os<=4'd11; end
                        default: str_idx<=0;
                    endcase
                end
            end

            4'd11: begin
                o_val32 <= freq_snaps[freq_out_idx];
                os <= O_FH;
            end

            O_FH: if (!tbusy && !tx_send) begin
                if (hex_pos<4'd8) begin
                    tx_byte<=hex_char(o_val32[31-hex_pos*4-:4]); tx_send<=1; hex_pos<=hex_pos+1;
                end else begin
                    tx_byte<=10; tx_send<=1;
                    freq_out_idx<=freq_out_idx+1; str_idx<=0; os<=O_FREQ;
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
    assign led = {hb[23], accum, pll_lock, sample_count[39:38]};
endmodule
