// entropy-source: deployable hardware TRNG experiment.
// Ring oscillators with runtime-configurable chain length and XOR collapse.
// See README.md for methodology.
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
    localparam integer BAUD = 115200;
    localparam integer NUM_RINGS = 64;
    localparam integer RINGS_PER_CH = 8;
    localparam integer NUM_CH = NUM_RINGS / RINGS_PER_CH;
    localparam integer RING_STAGES = 5;
    localparam integer WARMUP_SECONDS = 30;
    localparam integer FREQ_INTERVAL = CLK_HZ;
    localparam integer HEALTH_INTERVAL = CLK_HZ * 10;
    localparam integer STUCK_THRESHOLD = 1024;

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

    wire [NUM_RINGS-1:0] ring_out;
    genvar ri;
    generate for (ri=0; ri<NUM_RINGS; ri=ri+1) begin : gen_ring
        (* keep *) wire [RING_STAGES:0] r;
        assign r[0] = r[RING_STAGES];
        genvar st;
        for (st=0; st<RING_STAGES; st=st+1) begin : gen_st
            (* keep *) LUT4 #(.INIT(16'h5555)) inv(
                .Z(r[st+1]), .A(r[st]), .B(1'b0), .C(1'b0), .D(1'b0)
            );
        end
        assign ring_out[ri] = r[1];
    end endgenerate

    logic [NUM_RINGS-1:0] ring_sampled;
    always_ff @(posedge sys_clk) begin
        if (rst) ring_sampled <= 0;
        else     ring_sampled <= ring_out;
    end

    logic [NUM_CH-1:0] raw_bits;
    genvar ch;
    generate for (ch=0; ch<NUM_CH; ch=ch+1) begin : gen_ch
        always_comb begin
            raw_bits[ch] = ring_sampled[ch*RINGS_PER_CH] ^
                           ring_sampled[ch*RINGS_PER_CH+1] ^
                           ring_sampled[ch*RINGS_PER_CH+2] ^
                           ring_sampled[ch*RINGS_PER_CH+3] ^
                           ring_sampled[ch*RINGS_PER_CH+4] ^
                           ring_sampled[ch*RINGS_PER_CH+5] ^
                           ring_sampled[ch*RINGS_PER_CH+6] ^
                           ring_sampled[ch*RINGS_PER_CH+7];
        end
    end endgenerate

    logic [NUM_CH-1:0] prev_bits;
    logic              vn_phase;
    logic [NUM_CH-1:0] vn_valid;
    logic [NUM_CH-1:0] vn_bits;

    always_ff @(posedge sys_clk) begin
        vn_valid <= 0;
        if (rst) begin
            prev_bits <= 0;
            vn_phase  <= 0;
        end else begin
            if (!vn_phase) begin
                prev_bits <= raw_bits;
                vn_phase  <= 1;
            end else begin
                vn_phase <= 0;
                for (int c=0; c<NUM_CH; c=c+1) begin
                    if (prev_bits[c] != raw_bits[c]) begin
                        vn_valid[c] <= 1;
                        vn_bits[c]  <= prev_bits[c];
                    end
                end
            end
        end
    end

    logic [7:0]  ent_byte;
    logic [2:0]  ent_bit_idx;
    logic        ent_byte_ready;

    always_ff @(posedge sys_clk) begin
        ent_byte_ready <= 0;
        if (rst) begin
            ent_bit_idx <= 0;
        end else begin
            for (int c=0; c<NUM_CH; c=c+1) begin
                if (vn_valid[c] && !ent_byte_ready) begin
                    ent_byte[ent_bit_idx] <= vn_bits[c];
                    if (ent_bit_idx == 3'd7) begin
                        ent_byte_ready <= 1;
                        ent_bit_idx <= 0;
                    end else begin
                        ent_bit_idx <= ent_bit_idx + 1;
                    end
                end
            end
        end
    end

    logic ring_s0, ring_s1, ring_s2;
    wire ring_edge = ring_s1 && !ring_s2;
    always_ff @(posedge sys_clk) begin
        if (rst) begin ring_s0<=0; ring_s1<=0; ring_s2<=0; end
        else begin ring_s0<=ring_out[0]; ring_s1<=ring_s0; ring_s2<=ring_s1; end
    end

    logic [31:0] freq_count;
    logic [31:0] freq_timer;
    logic [31:0] freq_current;
    logic        freq_valid;
    logic [31:0] warmup_timer;
    logic        warmed_up;

    always_ff @(posedge sys_clk) begin
        freq_valid <= 0;
        if (rst) begin
            freq_count <= 0; freq_timer <= 0;
            freq_current <= 0; warmed_up <= 0;
            warmup_timer <= 0;
        end else begin
            if (ring_edge) freq_count <= freq_count + 1;
            freq_timer <= freq_timer + 1;
            if (freq_timer >= FREQ_INTERVAL) begin
                freq_current <= freq_count;
                freq_valid <= 1;
                freq_count <= 0;
                freq_timer <= 0;
            end
            if (!warmed_up) begin
                warmup_timer <= warmup_timer + 1;
                if (warmup_timer >= CLK_HZ * WARMUP_SECONDS)
                    warmed_up <= 1;
            end
        end
    end

    logic [NUM_CH-1:0] ch_stuck;
    logic [NUM_CH-1:0] ch_last_bit;
    logic [9:0]        stuck_cnt [0:NUM_CH-1];

    always_ff @(posedge sys_clk) begin
        if (rst) begin
            ch_stuck <= 0;
            for (int c=0; c<NUM_CH; c=c+1) begin
                ch_last_bit[c] <= 0;
                stuck_cnt[c] <= 0;
            end
        end else begin
            for (int c=0; c<NUM_CH; c=c+1) begin
                if (vn_valid[c]) begin
                    if (vn_bits[c] == ch_last_bit[c]) begin
                        if (stuck_cnt[c] < STUCK_THRESHOLD)
                            stuck_cnt[c] <= stuck_cnt[c] + 1;
                        if (stuck_cnt[c] >= STUCK_THRESHOLD - 1)
                            ch_stuck[c] <= 1;
                    end else begin
                        stuck_cnt[c] <= 0;
                        ch_stuck[c] <= 0;
                    end
                    ch_last_bit[c] <= vn_bits[c];
                end
            end
        end
    end

    localparam [3:0] O_WARMUP=0, O_W_HEX=1, O_W_NL=2,
                     O_READY=3, O_ENT=4, O_HEALTH=5, O_H_HEX=6, O_H_NL=7;
    logic [3:0] os;
    logic [31:0] health_timer;
    logic [31:0] o_val;
    logic [3:0]  hex_pos;
    logic [5:0]  str_idx;
    logic        health_pending;

    function automatic [7:0] hex_char(input [3:0] n);
        hex_char=(n<10)?(8'd48+{4'd0,n}):(8'd65+{4'd0,n}-8'd10);
    endfunction

    always_ff @(posedge sys_clk) begin
        tx_send <= 0;
        if (rst) begin
            os <= O_WARMUP; health_timer <= 0; str_idx <= 0; health_pending <= 0;
        end else begin
            if (warmed_up) begin
                health_timer <= health_timer + 1;
                if (health_timer >= HEALTH_INTERVAL) begin
                    health_timer <= 0;
                    health_pending <= 1;
                end
            end

            case (os)
                O_WARMUP: begin
                    if (warmed_up) begin
                        str_idx <= 0; os <= O_READY;
                    end else if (freq_valid && !tbusy && !tx_send) begin
                        tx_byte <= "W"; tx_send <= 1;
                        o_val <= freq_current;
                        hex_pos <= 0;
                        str_idx <= 0;
                        os <= O_W_HEX;
                    end
                end

                O_W_HEX: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin tx_byte <= ","; tx_send <= 1; str_idx <= 1; end
                        1: begin
                            if (hex_pos < 8) begin
                                tx_byte <= hex_char(o_val[31-hex_pos*4-:4]);
                                tx_send <= 1; hex_pos <= hex_pos + 1;
                            end else begin
                                os <= O_W_NL;
                            end
                        end
                        default: str_idx <= 1;
                    endcase
                end

                O_W_NL: if (!tbusy && !tx_send) begin
                    tx_byte <= 10; tx_send <= 1; os <= O_WARMUP;
                end

                O_READY: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin tx_byte <= "R"; tx_send <= 1; str_idx <= 1; end
                        1: begin tx_byte <= "E"; tx_send <= 1; str_idx <= 2; end
                        2: begin tx_byte <= "A"; tx_send <= 1; str_idx <= 3; end
                        3: begin tx_byte <= "D"; tx_send <= 1; str_idx <= 4; end
                        4: begin tx_byte <= "Y"; tx_send <= 1; str_idx <= 5; end
                        5: begin tx_byte <= 10;  tx_send <= 1; str_idx <= 6; end
                        default: os <= O_ENT;
                    endcase
                end

                O_ENT: begin
                    if (health_pending) begin
                        health_pending <= 0;
                        o_val <= freq_current;
                        hex_pos <= 0; str_idx <= 0;
                        os <= O_HEALTH;
                    end else if (ent_byte_ready && !tbusy && !tx_send) begin
                        tx_byte <= ent_byte;
                        tx_send <= 1;
                    end
                end

                O_HEALTH: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin tx_byte <= "H"; tx_send <= 1; str_idx <= 1; end
                        1: begin tx_byte <= ","; tx_send <= 1; str_idx <= 2; end
                        2: begin
                            if (hex_pos < 8) begin
                                tx_byte <= hex_char(o_val[31-hex_pos*4-:4]);
                                tx_send <= 1; hex_pos <= hex_pos + 1;
                            end else begin
                                str_idx <= 3;
                            end
                        end
                        3: begin tx_byte <= ","; tx_send <= 1; str_idx <= 4; end
                        4: begin tx_byte <= hex_char({4'd0, ch_stuck[7:4]}); tx_send <= 1; str_idx <= 5; end
                        5: begin tx_byte <= hex_char({4'd0, ch_stuck[3:0]}); tx_send <= 1; str_idx <= 6; end
                        6: os <= O_H_NL;
                        default: str_idx <= 6;
                    endcase
                end

                O_H_NL: if (!tbusy && !tx_send) begin
                    tx_byte <= 10; tx_send <= 1; os <= O_ENT;
                end

                default: os <= O_WARMUP;
            endcase
        end
    end

    logic [23:0] hb;
    always_ff @(posedge sys_clk) begin if(rst) hb<=0; else hb<=hb+1; end
    assign led = {hb[23], warmed_up, os==O_ENT, |ch_stuck, 1'b1};
endmodule
