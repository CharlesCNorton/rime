// seu-detector: single-event upset detection experiment.
// Uses triple-modular redundancy (TMR) flip-flop voting to detect
// radiation-induced bit flips. See README.md.
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

    localparam integer CLK_HZ        = 12500000;
    localparam integer BAUD          = 115200;
    localparam integer NUM_GROUPS    = 128;
    localparam integer BITS_PER_GRP  = 32;
    localparam integer TOTAL_BITS    = NUM_GROUPS * BITS_PER_GRP;
    localparam integer HEALTH_SEC    = 10;
    localparam integer COOLDOWN_SEC  = 1;
    localparam integer STARTUP_SEC   = 5;
    localparam integer RING_STAGES   = 5;

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

    (* keep *) wire [RING_STAGES:0] ref_ring;
    assign ref_ring[0] = ref_ring[RING_STAGES];
    genvar ri;
    generate for (ri=0; ri<RING_STAGES; ri=ri+1) begin : gen_ref_ring
        (* keep *) LUT4 #(.INIT(16'h5555)) inv(
            .Z(ref_ring[ri+1]), .A(ref_ring[ri]), .B(1'b0), .C(1'b0), .D(1'b0)
        );
    end endgenerate

    logic ring_s0, ring_s1, ring_s2;
    wire ring_edge = ring_s1 && !ring_s2;
    always_ff @(posedge sys_clk) begin
        if (rst) begin ring_s0<=0; ring_s1<=0; ring_s2<=0; end
        else begin ring_s0<=ref_ring[1]; ring_s1<=ring_s0; ring_s2<=ring_s1; end
    end

    logic [31:0] ring_count, ring_timer, ring_freq;
    always_ff @(posedge sys_clk) begin
        if (rst) begin ring_count<=0; ring_timer<=0; ring_freq<=0; end
        else begin
            if (ring_edge) ring_count <= ring_count + 1;
            ring_timer <= ring_timer + 1;
            if (ring_timer >= CLK_HZ) begin
                ring_freq <= ring_count;
                ring_count <= 0;
                ring_timer <= 0;
            end
        end
    end


    wire [31:0] det_word [0:NUM_GROUPS-1];

    logic        inject_we;
    logic [6:0]  inject_idx;
    logic [31:0] inject_val;
    logic        repair_we;
    logic [6:0]  repair_idx;

    logic inject_armed;
    always_ff @(posedge sys_clk) begin
        inject_we <= 0;
        if (rst) begin
            inject_armed <= 0;
        end else if (rx_v) begin
            if (inject_armed) begin
                inject_armed <= 0;
                inject_we <= 1;
                inject_idx <= rx_d[6:0];
                inject_val <= scan_data ^ uptime_counter;
            end else if (rx_d == 8'hFF) begin
                inject_armed <= 1;
            end else begin
                inject_armed <= 0;
            end
        end
    end

    genvar gi;
    generate
        for (gi = 0; gi < NUM_GROUPS; gi = gi + 1) begin : gen_det
            (* keep *) reg [31:0] word;
            assign det_word[gi] = word;
            always_ff @(posedge sys_clk) begin
                if (rst)
                    word <= 32'hA5A5A5A5 ^ {gi[7:0], gi[7:0], gi[7:0], gi[7:0]};
                else if (inject_we && inject_idx == gi[6:0])
                    word <= inject_val;
                else if (repair_we && repair_idx == gi[6:0])
                    word <= 32'hA5A5A5A5 ^ {gi[7:0], gi[7:0], gi[7:0], gi[7:0]};
            end
        end
    endgenerate


    logic [6:0]  scan_idx;
    logic        scan_phase;
    logic [31:0] scan_data;
    logic [31:0] scan_expected;
    logic [31:0] total_scans;
    logic [15:0] total_flips;
    logic [31:0] uptime_seconds;
    logic [31:0] uptime_counter;

    logic [NUM_GROUPS-1:0] reported;
    logic [31:0] cooldown_timer;

    logic        event_pending;
    logic        event_ack;
    logic [6:0]  event_idx;
    logic [31:0] event_xor;
    logic [31:0] event_scan;

    logic [31:0] startup_timer;
    logic        started;

    always_ff @(posedge sys_clk) begin
        if (rst) begin
            scan_idx <= 0; scan_phase <= 0;
            total_scans <= 0; total_flips <= 0;
            uptime_seconds <= 0; uptime_counter <= 0;
            reported <= 0; cooldown_timer <= 0;
            event_pending <= 0;
            startup_timer <= 0; started <= 0;
        end else begin
            if (!started) begin
                startup_timer <= startup_timer + 1;
                if (startup_timer >= CLK_HZ * STARTUP_SEC)
                    started <= 1;
            end

            uptime_counter <= uptime_counter + 1;
            if (uptime_counter >= CLK_HZ) begin
                uptime_counter <= 0;
                uptime_seconds <= uptime_seconds + 1;
            end

            cooldown_timer <= cooldown_timer + 1;
            if (cooldown_timer >= CLK_HZ * COOLDOWN_SEC) begin
                cooldown_timer <= 0;
                reported <= 0;
            end

            repair_we <= 0;
            if (event_ack) begin
                event_pending <= 0;
                repair_we <= 1;
                repair_idx <= event_idx;
            end

            if (started) begin
                case (scan_phase)
                    1'b0: begin
                        scan_data <= det_word[scan_idx];
                        scan_expected <= 32'hA5A5A5A5 ^
                            {{1'b0, scan_idx}, {1'b0, scan_idx},
                             {1'b0, scan_idx}, {1'b0, scan_idx}};
                        scan_phase <= 1;
                    end
                    1'b1: begin
                        if (scan_data != scan_expected &&
                            !reported[scan_idx] &&
                            !event_pending) begin
                            event_pending <= 1;
                            event_idx     <= scan_idx;
                            event_xor     <= scan_data ^ scan_expected;
                            event_scan    <= total_scans;
                            total_flips   <= total_flips + 1;
                            reported[scan_idx] <= 1;
                        end
                        if (scan_idx == NUM_GROUPS[6:0] - 7'd1) begin
                            scan_idx <= 0;
                            total_scans <= total_scans + 1;
                        end else begin
                            scan_idx <= scan_idx + 1;
                        end
                        scan_phase <= 0;
                    end
                endcase
            end
        end
    end

    localparam [3:0] O_IDLE=0, O_HDR=1, O_CFG=2, O_MAIN=3,
                     O_EVENT=4, O_EV_HEX=5, O_EV_NL=6,
                     O_HEALTH=7, O_H_HEX=8, O_H_NL=9;
    logic [3:0]  os;
    logic [31:0] health_timer;
    logic        health_pending;
    logic [31:0] o_val;
    logic [3:0]  hex_pos;
    logic [5:0]  str_idx;

    function automatic [7:0] hex_char(input [3:0] n);
        hex_char = (n < 10) ? (8'd48 + {4'd0, n}) : (8'd65 + {4'd0, n} - 8'd10);
    endfunction

    function automatic [7:0] hdr_char(input [5:0] idx);
        case (idx)
            0:hdr_char=13; 1:hdr_char=10;
            2:hdr_char="S"; 3:hdr_char="E"; 4:hdr_char="U"; 5:hdr_char=" ";
            6:hdr_char="D"; 7:hdr_char="E"; 8:hdr_char="T"; 9:hdr_char="E";
            10:hdr_char="C"; 11:hdr_char="T"; 12:hdr_char="O"; 13:hdr_char="R";
            14:hdr_char=" "; 15:hdr_char="E"; 16:hdr_char="C"; 17:hdr_char="P";
            18:hdr_char="5"; 19:hdr_char=13; 20:hdr_char=10;
            default: hdr_char=0;
        endcase
    endfunction

    always_ff @(posedge sys_clk) begin
        tx_send <= 0;
        event_ack <= 0;
        if (rst) begin
            os <= O_IDLE; health_timer <= 0; health_pending <= 0;
            str_idx <= 0;
        end else begin
            if (started) begin
                health_timer <= health_timer + 1;
                if (health_timer >= CLK_HZ * HEALTH_SEC) begin
                    health_timer <= 0;
                    health_pending <= 1;
                end
            end

            case (os)
                O_IDLE: if (started) begin str_idx <= 0; os <= O_HDR; end

                O_HDR: if (!tbusy && !tx_send) begin
                    if (str_idx < 6'd21) begin
                        tx_byte <= hdr_char(str_idx);
                        tx_send <= 1;
                        str_idx <= str_idx + 1;
                    end else begin
                        str_idx <= 0;
                        os <= O_CFG;
                    end
                end

                O_CFG: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin tx_byte<="C"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                        2: begin tx_byte<="0"; tx_send<=1; str_idx<=3; end
                        3: begin tx_byte<="0"; tx_send<=1; str_idx<=4; end
                        4: begin tx_byte<="8"; tx_send<=1; str_idx<=5; end
                        5: begin tx_byte<="0"; tx_send<=1; str_idx<=6; end
                        6: begin tx_byte<=","; tx_send<=1; str_idx<=7; end
                        7: begin tx_byte<="0"; tx_send<=1; str_idx<=8; end
                        8: begin tx_byte<="0"; tx_send<=1; str_idx<=9; end
                        9: begin tx_byte<="2"; tx_send<=1; str_idx<=10; end
                        10:begin tx_byte<="0"; tx_send<=1; str_idx<=11; end
                        11:begin tx_byte<=","; tx_send<=1; str_idx<=12; end
                        12:begin tx_byte<="A"; tx_send<=1; str_idx<=13; end
                        13:begin tx_byte<="5"; tx_send<=1; str_idx<=14; end
                        14:begin tx_byte<="A"; tx_send<=1; str_idx<=15; end
                        15:begin tx_byte<="5"; tx_send<=1; str_idx<=16; end
                        16:begin tx_byte<="A"; tx_send<=1; str_idx<=17; end
                        17:begin tx_byte<="5"; tx_send<=1; str_idx<=18; end
                        18:begin tx_byte<="A"; tx_send<=1; str_idx<=19; end
                        19:begin tx_byte<="5"; tx_send<=1; str_idx<=20; end
                        20:begin tx_byte<=10;  tx_send<=1; os<=O_MAIN; end
                        default: str_idx<=20;
                    endcase
                end

                O_MAIN: begin
                    if (event_pending && !tbusy && !tx_send) begin
                        str_idx <= 0;
                        os <= O_EVENT;
                    end else if (health_pending && !tbusy && !tx_send) begin
                        health_pending <= 0;
                        str_idx <= 0;
                        os <= O_HEALTH;
                    end
                end

                O_EVENT: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin tx_byte<="F"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                        2: begin tx_byte<=hex_char({1'b0, event_idx[6:4]}); tx_send<=1; str_idx<=3; end
                        3: begin tx_byte<=hex_char(event_idx[3:0]); tx_send<=1; str_idx<=4; end
                        4: begin tx_byte<=","; tx_send<=1; str_idx<=5; end
                        5: begin o_val<=event_xor; hex_pos<=0; os<=O_EV_HEX; str_idx<=0; end
                        default: str_idx<=5;
                    endcase
                end

                O_EV_HEX: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin
                            if (hex_pos < 8) begin
                                tx_byte <= hex_char(o_val[31 - hex_pos*4 -: 4]);
                                tx_send <= 1; hex_pos <= hex_pos + 1;
                            end else begin
                                str_idx <= 1;
                            end
                        end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                        2: begin o_val<=event_scan; hex_pos<=0; str_idx<=3; end
                        3: begin
                            if (hex_pos < 8) begin
                                tx_byte <= hex_char(o_val[31 - hex_pos*4 -: 4]);
                                tx_send <= 1; hex_pos <= hex_pos + 1;
                            end else begin
                                os <= O_EV_NL;
                            end
                        end
                        default: str_idx <= 3;
                    endcase
                end

                O_EV_NL: if (!tbusy && !tx_send) begin
                    tx_byte <= 10; tx_send <= 1;
                    event_ack <= 1;
                    os <= O_MAIN;
                end

                O_HEALTH: if (!tbusy && !tx_send) begin
                    case (str_idx)
                        0: begin tx_byte<="S"; tx_send<=1; str_idx<=1; end
                        1: begin tx_byte<=","; tx_send<=1; str_idx<=2; end
                        2: begin o_val<=total_scans; hex_pos<=0; str_idx<=3; end
                        3: begin
                            if (hex_pos < 8) begin
                                tx_byte <= hex_char(o_val[31 - hex_pos*4 -: 4]);
                                tx_send <= 1; hex_pos <= hex_pos + 1;
                            end else str_idx <= 4;
                        end
                        4: begin tx_byte<=","; tx_send<=1; str_idx<=5; end
                        5: begin tx_byte<=hex_char(total_flips[15:12]); tx_send<=1; str_idx<=6; end
                        6: begin tx_byte<=hex_char(total_flips[11:8]);  tx_send<=1; str_idx<=7; end
                        7: begin tx_byte<=hex_char(total_flips[7:4]);   tx_send<=1; str_idx<=8; end
                        8: begin tx_byte<=hex_char(total_flips[3:0]);   tx_send<=1; str_idx<=9; end
                        9: begin tx_byte<=","; tx_send<=1; str_idx<=10; end
                        10:begin o_val<=uptime_seconds; hex_pos<=0; str_idx<=11; end
                        11:begin
                            if (hex_pos < 8) begin
                                tx_byte <= hex_char(o_val[31 - hex_pos*4 -: 4]);
                                tx_send <= 1; hex_pos <= hex_pos + 1;
                            end else str_idx <= 12;
                        end
                        12:begin tx_byte<=","; tx_send<=1; str_idx<=13; end
                        13:begin o_val<=ring_freq; hex_pos<=0; str_idx<=14; end
                        14:begin
                            if (hex_pos < 8) begin
                                tx_byte <= hex_char(o_val[31 - hex_pos*4 -: 4]);
                                tx_send <= 1; hex_pos <= hex_pos + 1;
                            end else os <= O_H_NL;
                        end
                        default: str_idx <= 14;
                    endcase
                end

                O_H_NL: if (!tbusy && !tx_send) begin
                    tx_byte <= 10; tx_send <= 1;
                    os <= O_MAIN;
                end

                default: os <= O_IDLE;
            endcase
        end
    end

    logic [23:0] hb;
    always_ff @(posedge sys_clk) begin if (rst) hb<=0; else hb<=hb+1; end
    assign led = {hb[23], started && scan_phase==0, started, |total_flips[15:0], 1'b1};
endmodule
