// EMBER: Entropy Measurement and Board-level Environmental Randomness.
//
// Hardware true random number generator. 192 ring oscillators in three
// thermally isolated paths (64 per path), majority-voted, Von Neumann
// debiased, LFSR whitened, then AES-128-CBC conditioned. NIST SP 800-90B
// health tests run continuously. Requires 60-second thermal warmup.
//
// Standalone firmware image — takes 100% of the FPGA when loaded.
// Communicates entropy bytes and health status over UART.

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
    localparam integer PATHS = 3;
    localparam integer RINGS_PER_PATH = 64;
    localparam integer RINGS_PER_CH = 8;
    localparam integer NUM_CH = RINGS_PER_PATH / RINGS_PER_CH;
    localparam integer TOTAL_RINGS = PATHS * RINGS_PER_PATH;
    localparam integer RING_STAGES = 5;
    localparam integer WARMUP_SECONDS = 60;
    // SEED_DELAY_SECONDS must be <= WARMUP_SECONDS because warmup_timer
    // stops counting when warmed_up fires. A value > WARMUP_SECONDS makes
    // the aes_key_loaded condition unreachable, blocking all conditioned output.
    localparam integer SEED_DELAY_SECONDS = 60;
    localparam integer FREQ_INTERVAL = CLK_HZ;
    localparam integer HEALTH_INTERVAL = CLK_HZ * 10;
    localparam integer STUCK_THRESHOLD = 1024;

    logic [1:0] clk_div;
    wire sys_clk = clk_div[1];
    always_ff @(posedge clk) begin
        if (~button[0]) clk_div<=0; else clk_div<=clk_div+1;
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

    wire [TOTAL_RINGS-1:0] ring_out;
    genvar ri;
    generate for (ri=0; ri<TOTAL_RINGS; ri=ri+1) begin : gen_ring
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

    logic [TOTAL_RINGS-1:0] ring_sampled;
    always_ff @(posedge sys_clk) begin
        if (rst) ring_sampled <= 0;
        else     ring_sampled <= ring_out;
    end

    logic [NUM_CH-1:0] path_bits [0:PATHS-1];
    genvar p, ch;
    generate
        for (p=0; p<PATHS; p=p+1) begin : gen_path
            for (ch=0; ch<NUM_CH; ch=ch+1) begin : gen_ch
                always_comb begin
                    logic [7:0] group;
                    group = ring_sampled[(p*RINGS_PER_PATH + ch*RINGS_PER_CH) +: RINGS_PER_CH];
                    path_bits[p][ch] = ^group;
                end
            end
        end
    endgenerate

    logic [NUM_CH-1:0] voted_bits;
    always_comb begin
        for (int c=0; c<NUM_CH; c=c+1) begin
            voted_bits[c] = (path_bits[0][c] & path_bits[1][c]) |
                            (path_bits[0][c] & path_bits[2][c]) |
                            (path_bits[1][c] & path_bits[2][c]);
        end
    end

    logic [NUM_CH-1:0] prev_bits;
    logic              vn_phase;
    logic [NUM_CH-1:0] vn_valid;
    logic [NUM_CH-1:0] vn_bits;

    always_ff @(posedge sys_clk) begin
        vn_valid <= 0;
        if (rst) begin prev_bits<=0; vn_phase<=0; end
        else begin
            if (!vn_phase) begin
                prev_bits <= voted_bits;
                vn_phase  <= 1;
            end else begin
                vn_phase <= 0;
                for (int c=0; c<NUM_CH; c=c+1) begin
                    if (prev_bits[c] != voted_bits[c]) begin
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
        if (rst) ent_bit_idx <= 0;
        else begin
            for (int c=0; c<NUM_CH; c=c+1) begin
                if (vn_valid[c] && !ent_byte_ready) begin
                    ent_byte[ent_bit_idx] <= vn_bits[c];
                    if (ent_bit_idx==3'd7) begin
                        ent_byte_ready <= 1;
                        ent_bit_idx <= 0;
                    end else ent_bit_idx <= ent_bit_idx + 1;
                end
            end
        end
    end

    logic [31:0] lfsr;
    logic [1:0]  lfsr_seed_idx;
    logic        lfsr_seeded;
    logic [7:0]  whitened_byte;
    logic        whitened_ready;

    wire lfsr_fb = lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0];

    logic [2:0] lfsr_step_cnt;

    always_ff @(posedge sys_clk) begin
        whitened_ready <= 0;
        if (rst) begin
            lfsr <= 32'd1;
            lfsr_seed_idx <= 0;
            lfsr_seeded <= 0;
            lfsr_step_cnt <= 0;
        end else if (!lfsr_seeded && ent_byte_ready && warmed_up) begin
            case (lfsr_seed_idx)
                2'd0: lfsr[7:0]   <= ent_byte;
                2'd1: lfsr[15:8]  <= ent_byte;
                2'd2: lfsr[23:16] <= ent_byte;
                2'd3: begin
                    lfsr[31:24] <= ent_byte;
                    lfsr_seeded <= 1;
                end
            endcase
            lfsr_seed_idx <= lfsr_seed_idx + 1;
        end else if (lfsr_seeded) begin
            lfsr <= {lfsr[30:0], lfsr_fb};
            if (lfsr == 32'd0) lfsr <= 32'd1;

            if (ent_byte_ready) begin
                whitened_byte <= ent_byte ^ lfsr[7:0];
                whitened_ready <= 1;
            end
        end
    end

    (* ram_style = "block" *)
    reg [7:0] burst_buf [0:4095];
    logic [11:0] buf_wr, buf_rd;
    wire         buf_empty = (buf_wr == buf_rd);
    wire [11:0]  buf_count = buf_wr - buf_rd;
    logic [7:0]  buf_rd_data;
    logic        buf_rd_valid;

    always_ff @(posedge sys_clk) begin
        buf_rd_data <= burst_buf[buf_rd];
    end

    always_ff @(posedge sys_clk) begin
        if (rst) begin buf_wr<=0; buf_rd<=0; buf_rd_valid<=0; end
        else begin
            if (whitened_ready && buf_count < 12'd4090)  begin
                burst_buf[buf_wr] <= whitened_byte;
                buf_wr <= buf_wr + 1;
            end
        end
    end

    logic [127:0] aes_plaintext;
    logic [127:0] aes_key;
    logic [127:0] aes_iv;
    logic [127:0] aes_ciphertext;
    logic         aes_start, aes_done, aes_busy;
    logic [3:0]   aes_collect_idx;
    logic         aes_key_loaded;
    logic [3:0]   aes_key_idx;
    logic [3:0]   aes_out_idx;
    logic         aes_out_valid;
    logic [7:0]   conditioned_byte;
    logic         conditioned_ready;

    aes128 AES (
        .clk(sys_clk), .rst(rst),
        .start(aes_start), .plaintext(aes_plaintext ^ aes_iv),
        .key(aes_key),
        .done(aes_done), .busy(aes_busy), .ciphertext(aes_ciphertext)
    );

    always_ff @(posedge sys_clk) begin
        aes_start <= 0;
        conditioned_ready <= 0;
        if (rst) begin
            aes_collect_idx <= 0;
            aes_key_loaded <= 0;
            aes_key_idx <= 0;
            aes_iv <= 128'd0;
            aes_out_idx <= 0;
            aes_out_valid <= 0;
        end else if (!aes_key_loaded && whitened_ready && warmup_timer >= CLK_HZ * SEED_DELAY_SECONDS) begin
            aes_key[aes_key_idx*8 +: 8] <= whitened_byte;
            if (aes_key_idx == 4'd15)
                aes_key_loaded <= 1;
            else
                aes_key_idx <= aes_key_idx + 1;
        end else if (aes_key_loaded && !aes_out_valid) begin
            if (whitened_ready && !aes_busy) begin
                aes_plaintext[aes_collect_idx*8 +: 8] <= whitened_byte;
                if (aes_collect_idx == 4'd15) begin
                    aes_start <= 1;
                    aes_collect_idx <= 0;
                end else
                    aes_collect_idx <= aes_collect_idx + 1;
            end
            if (aes_done) begin
                aes_iv <= aes_ciphertext;
                aes_out_valid <= 1;
                aes_out_idx <= 0;
            end
        end else if (aes_out_valid) begin
            conditioned_byte <= aes_ciphertext[aes_out_idx*8 +: 8];
            conditioned_ready <= 1;
            if (aes_out_idx == 4'd15)
                aes_out_valid <= 0;
            else
                aes_out_idx <= aes_out_idx + 1;
        end
    end

    logic [7:0]  apt_ref;
    logic [9:0]  apt_count;
    logic [9:0]  apt_window_idx;
    logic        apt_alarm;

    always_ff @(posedge sys_clk) begin
        if (rst) begin
            apt_count <= 0; apt_window_idx <= 0; apt_alarm <= 0;
        end else if (conditioned_ready) begin
            if (apt_window_idx == 0) begin
                apt_ref <= conditioned_byte;
                apt_count <= 0;
                apt_window_idx <= 1;
            end else begin
                if (conditioned_byte == apt_ref)
                    apt_count <= apt_count + 1;
                if (apt_count >= 10'd325)
                    apt_alarm <= 1;
                if (apt_window_idx == 10'd511) begin
                    apt_window_idx <= 0;
                    if (apt_count < 10'd325)
                        apt_alarm <= 0;
                end else
                    apt_window_idx <= apt_window_idx + 1;
            end
        end
    end

    (* ram_style = "block" *)
    reg [9:0] me_byte_count [0:255];
    logic [7:0]  me_bram_addr;
    logic [9:0]  me_bram_rd;
    logic        me_bram_we;
    logic [9:0]  me_bram_wd;

    always_ff @(posedge sys_clk) begin
        me_bram_rd <= me_byte_count[me_bram_addr];
        if (me_bram_we) me_byte_count[me_bram_addr] <= me_bram_wd;
    end

    logic [9:0]  me_window_idx;
    logic [9:0]  me_max_count;
    logic [9:0]  me_last_max;
    logic [1:0]  me_state;
    logic [7:0]  me_clear_idx;
    logic [7:0]  me_pending_byte;

    always_ff @(posedge sys_clk) begin
        me_bram_we <= 0;
        if (rst) begin
            me_window_idx <= 0; me_max_count <= 0; me_last_max <= 0;
            me_state <= 0; me_clear_idx <= 0;
        end else case (me_state)
            2'd0: begin
                if (me_clear_idx != 0) begin
                    me_bram_addr <= me_clear_idx;
                    me_bram_wd <= 0;
                    me_bram_we <= 1;
                    if (me_clear_idx == 8'd255)
                        me_clear_idx <= 0;
                    else
                        me_clear_idx <= me_clear_idx + 1;
                end else if (whitened_ready && warmed_up) begin
                    me_bram_addr <= whitened_byte;
                    me_pending_byte <= whitened_byte;
                    me_state <= 2'd1;
                end
            end
            2'd1: begin
                me_state <= 2'd2;
            end
            2'd2: begin
                me_bram_addr <= me_pending_byte;
                me_bram_wd <= me_bram_rd + 1;
                me_bram_we <= 1;
                if (me_bram_rd + 1 > me_max_count)
                    me_max_count <= me_bram_rd + 1;
                me_window_idx <= me_window_idx + 1;
                if (me_window_idx == 10'd1023) begin
                    me_last_max <= me_max_count;
                    me_max_count <= 0;
                    me_window_idx <= 0;
                    me_clear_idx <= 1;
                    me_bram_addr <= 0;
                    me_bram_wd <= 0;
                    me_bram_we <= 1;
                end
                me_state <= 2'd0;
            end
            default: me_state <= 2'd0;
        endcase
    end

    logic ring_s0, ring_s1, ring_s2;
    wire ring_edge = ring_s1 && !ring_s2;
    always_ff @(posedge sys_clk) begin
        if (rst) begin ring_s0<=0; ring_s1<=0; ring_s2<=0; end
        else begin ring_s0<=ring_out[0]; ring_s1<=ring_s0; ring_s2<=ring_s1; end
    end

    logic [31:0] freq_count, freq_timer, freq_current;
    logic        freq_valid;
    logic [31:0] warmup_timer;
    logic        warmed_up;

    always_ff @(posedge sys_clk) begin
        freq_valid <= 0;
        if (rst) begin
            freq_count<=0; freq_timer<=0; freq_current<=0;
            warmed_up<=0; warmup_timer<=0;
        end else begin
            if (ring_edge) freq_count<=freq_count+1;
            freq_timer<=freq_timer+1;
            if (freq_timer>=FREQ_INTERVAL) begin
                freq_current<=freq_count; freq_valid<=1;
                freq_count<=0; freq_timer<=0;
            end
            if (!warmed_up) begin
                warmup_timer<=warmup_timer+1;
                if (warmup_timer>=CLK_HZ*WARMUP_SECONDS) warmed_up<=1;
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
                ch_last_bit[c]<=0; stuck_cnt[c]<=0;
            end
        end else begin
            for (int c=0; c<NUM_CH; c=c+1) begin
                if (vn_valid[c]) begin
                    if (vn_bits[c]==ch_last_bit[c]) begin
                        if (stuck_cnt[c]<STUCK_THRESHOLD) stuck_cnt[c]<=stuck_cnt[c]+1;
                        if (stuck_cnt[c]>=STUCK_THRESHOLD-1) ch_stuck[c]<=1;
                    end else begin stuck_cnt[c]<=0; ch_stuck[c]<=0; end
                    ch_last_bit[c]<=vn_bits[c];
                end
            end
        end
    end

    logic [31:0] agree_count, disagree_count;
    always_ff @(posedge sys_clk) begin
        if (rst) begin agree_count<=0; disagree_count<=0; end
        else if (warmed_up) begin
            if (path_bits[0][0]==path_bits[1][0] && path_bits[1][0]==path_bits[2][0])
                agree_count <= agree_count + 1;
            else
                disagree_count <= disagree_count + 1;
        end
    end

    logic [15:0] ac_agree, ac_total;
    logic        ac_last_bit;
    logic [15:0] ac_last_agree;

    always_ff @(posedge sys_clk) begin
        if (rst) begin ac_agree<=0; ac_total<=0; ac_last_bit<=0; ac_last_agree<=0; end
        else begin
            if (warmed_up) begin
                ac_total <= ac_total + 1;
                if (voted_bits[0] == ac_last_bit) ac_agree <= ac_agree + 1;
                ac_last_bit <= voted_bits[0];
                if (ac_total == 16'hFFFF) begin
                    ac_last_agree <= ac_agree;
                    ac_agree <= 0;
                    ac_total <= 0;
                end
            end
        end
    end

    logic [15:0] runs_count, runs_total;
    logic        runs_last;
    logic [15:0] runs_last_count;

    always_ff @(posedge sys_clk) begin
        if (rst) begin runs_count<=0; runs_total<=0; runs_last<=0; runs_last_count<=0; end
        else if (warmed_up) begin
            runs_total <= runs_total + 1;
            if (voted_bits[0] != runs_last) runs_count <= runs_count + 1;
            runs_last <= voted_bits[0];
            if (runs_total == 16'hFFFF) begin
                runs_last_count <= runs_count;
                runs_count <= 0;
                runs_total <= 0;
            end
        end
    end

    reg [15:0] comp_bitmap [0:1023];
    logic [9:0]  comp_bram_addr;
    logic [15:0] comp_bram_rd;
    logic        comp_bram_we;
    logic [15:0] comp_bram_wd;

    always_ff @(posedge sys_clk) begin
        comp_bram_rd <= comp_bitmap[comp_bram_addr];
        if (comp_bram_we) comp_bitmap[comp_bram_addr] <= comp_bram_wd;
    end

    logic [7:0]  comp_prev_byte;
    logic [13:0] comp_hash;
    logic [15:0] comp_occupied;
    logic [15:0] comp_last_result;
    logic [10:0] comp_pair_count;
    logic        comp_alarm;
    logic [2:0]  comp_state;

    localparam [2:0] CS_IDLE=0, CS_HASH=1, CS_RDWAIT=2, CS_CHECK=3, CS_CLEAR=4;
    logic [9:0] comp_clear_addr;

    always_ff @(posedge sys_clk) begin
        comp_bram_we <= 0;
        if (rst) begin
            comp_prev_byte<=0; comp_occupied<=0; comp_last_result<=0;
            comp_pair_count<=0; comp_alarm<=0; comp_state<=CS_IDLE;
            comp_clear_addr<=0;
        end else case (comp_state)
            CS_IDLE: begin
                if (whitened_ready) begin
                    comp_hash <= {comp_prev_byte[5:0], whitened_byte};
                    comp_prev_byte <= whitened_byte;
                    comp_state <= CS_HASH;
                end
            end

            CS_HASH: begin
                comp_bram_addr <= comp_hash[13:4];
                comp_state <= CS_RDWAIT;
            end

            CS_RDWAIT: begin
                comp_state <= CS_CHECK;
            end

            CS_CHECK: begin
                if (!comp_bram_rd[comp_hash[3:0]]) begin
                    comp_occupied <= comp_occupied + 1;
                end
                comp_bram_addr <= comp_hash[13:4];
                comp_bram_wd <= comp_bram_rd | (16'd1 << comp_hash[3:0]);
                comp_bram_we <= 1;

                comp_pair_count <= comp_pair_count + 1;
                if (comp_pair_count == 11'd1023) begin
                    comp_last_result <= comp_occupied;
                    comp_alarm <= (comp_occupied < 16'd900);
                    comp_occupied <= 0;
                    comp_pair_count <= 0;
                    comp_clear_addr <= 0;
                    comp_state <= CS_CLEAR;
                end else begin
                    comp_state <= CS_IDLE;
                end
            end

            CS_CLEAR: begin
                comp_bram_addr <= comp_clear_addr;
                comp_bram_wd <= 16'd0;
                comp_bram_we <= 1;
                if (comp_clear_addr == 10'd1023)
                    comp_state <= CS_IDLE;
                else
                    comp_clear_addr <= comp_clear_addr + 1;
            end

            default: comp_state <= CS_IDLE;
        endcase
    end

    localparam [4:0] O_WARMUP=0, O_W_HEX=1, O_W_NL=2,
                     O_READY=3, O_ENT=4, O_HEALTH=5, O_H_HEX=6, O_H_NL=7,
                     O_BUF_POP=8;
    logic [4:0] os;
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
            os<=O_WARMUP; health_timer<=0; str_idx<=0; health_pending<=0;
        end else begin
            if (warmed_up) begin
                health_timer<=health_timer+1;
                if (health_timer>=HEALTH_INTERVAL) begin
                    health_timer<=0; health_pending<=1;
                end
            end

            case (os)
                O_WARMUP: begin
                    if (warmed_up) begin str_idx<=0; os<=O_READY; end
                    else if (freq_valid && !tbusy && !tx_send) begin
                        tx_byte<="W"; tx_send<=1;
                        o_val<=freq_current; hex_pos<=0; str_idx<=0; os<=O_W_HEX;
                    end
                end
                O_W_HEX: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin tx_byte<=","; tx_send<=1; str_idx<=1; end
                        1: if (hex_pos<8) begin
                            tx_byte<=hex_char(o_val[31-hex_pos*4-:4]);
                            tx_send<=1; hex_pos<=hex_pos+1;
                        end else os<=O_W_NL;
                        default: str_idx<=1;
                    endcase
                end
                O_W_NL: if (!tbusy&&!tx_send) begin tx_byte<=10; tx_send<=1; os<=O_WARMUP; end
                O_READY: if (!tbusy&&!tx_send) begin
                    case (str_idx)
                        0: begin tx_byte<="R"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<="E"; tx_send<=1; str_idx<=2; end
                        2: begin tx_byte<="A"; tx_send<=1; str_idx<=3; end
                        3: begin tx_byte<="D"; tx_send<=1; str_idx<=4; end
                        4: begin tx_byte<="Y"; tx_send<=1; str_idx<=5; end
                        5: begin tx_byte<=10;  tx_send<=1; str_idx<=6; end
                        default: os<=O_ENT;
                    endcase
                end
                O_ENT: begin
                    if (health_pending) begin
                        health_pending<=0;
                        o_val<=freq_current; hex_pos<=0; str_idx<=0; os<=O_HEALTH;
                    end else if (conditioned_ready && !tbusy && !tx_send) begin
                        tx_byte <= conditioned_byte;
                        tx_send <= 1;
                    end
                end
                O_HEALTH: if (!tbusy&&!tx_send) begin
                    case (str_idx)
                        0: begin tx_byte<="H"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                        2: if (hex_pos<8) begin
                            tx_byte<=hex_char(o_val[31-hex_pos*4-:4]);
                            tx_send<=1; hex_pos<=hex_pos+1;
                        end else str_idx<=3;
                        3: begin tx_byte<=","; tx_send<=1; str_idx<=4; end
                        4: begin tx_byte<=hex_char({4'd0,ch_stuck[7:4]}); tx_send<=1; str_idx<=5; end
                        5: begin tx_byte<=hex_char({4'd0,ch_stuck[3:0]}); tx_send<=1; str_idx<=6; end
                        6: begin tx_byte<=","; tx_send<=1; str_idx<=7; end
                        7: begin tx_byte<=hex_char(comp_last_result[15:12]); tx_send<=1; str_idx<=8; end
                        8: begin tx_byte<=hex_char(comp_last_result[11:8]); tx_send<=1; str_idx<=9; end
                        9: begin tx_byte<=hex_char(comp_last_result[7:4]); tx_send<=1; str_idx<=10; end
                        10:begin tx_byte<=hex_char(comp_last_result[3:0]); tx_send<=1; str_idx<=11; end
                        11:begin tx_byte<=","; tx_send<=1; str_idx<=12; end
                        12:begin tx_byte<=hex_char(ac_last_agree[15:12]); tx_send<=1; str_idx<=13; end
                        13:begin tx_byte<=hex_char(ac_last_agree[11:8]); tx_send<=1; str_idx<=14; end
                        14:begin tx_byte<=hex_char(ac_last_agree[7:4]); tx_send<=1; str_idx<=15; end
                        15:begin tx_byte<=hex_char(ac_last_agree[3:0]); tx_send<=1; str_idx<=16; end
                        16:begin tx_byte<=","; tx_send<=1; str_idx<=17; end
                        17:begin tx_byte<=hex_char(runs_last_count[15:12]); tx_send<=1; str_idx<=18; end
                        18:begin tx_byte<=hex_char(runs_last_count[11:8]); tx_send<=1; str_idx<=19; end
                        19:begin tx_byte<=hex_char(runs_last_count[7:4]); tx_send<=1; str_idx<=20; end
                        20:begin tx_byte<=hex_char(runs_last_count[3:0]); tx_send<=1; str_idx<=21; end
                        21:begin tx_byte<=","; tx_send<=1; str_idx<=22; end
                        22:begin tx_byte<=hex_char(agree_count[15:12]); tx_send<=1; str_idx<=23; end
                        23:begin tx_byte<=hex_char(agree_count[11:8]); tx_send<=1; str_idx<=24; end
                        24:begin tx_byte<=hex_char(agree_count[7:4]); tx_send<=1; str_idx<=25; end
                        25:begin tx_byte<=hex_char(agree_count[3:0]); tx_send<=1; str_idx<=26; end
                        26:begin tx_byte<=","; tx_send<=1; str_idx<=27; end
                        27:begin tx_byte<=hex_char({2'b0, me_last_max[9:8]}); tx_send<=1; str_idx<=28; end
                        28:begin tx_byte<=hex_char(me_last_max[7:4]); tx_send<=1; str_idx<=29; end
                        29:begin tx_byte<=hex_char(me_last_max[3:0]); tx_send<=1; str_idx<=30; end
                        30: os<=O_H_NL;
                        default: str_idx<=26;
                    endcase
                end
                O_H_NL: if (!tbusy&&!tx_send) begin tx_byte<=10; tx_send<=1; os<=O_ENT; end
                default: os<=O_WARMUP;
            endcase
        end
    end

    logic [23:0] hb;
    always_ff @(posedge sys_clk) begin if(rst) hb<=0; else hb<=hb+1; end
    assign led = {hb[23], warmed_up, os==O_ENT, |ch_stuck | apt_alarm, 1'b1};
endmodule
