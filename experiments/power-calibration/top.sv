// power-calibration: self-contained thermal tomography experiment.
// Maps die temperature distribution using ring-oscillator frequency
// as a thermal proxy. See README.md.
module top (
    input  wire       clk,
    input  wire       usb_rx,
    output wire       usb_tx,
    output logic [4:0] led,
    input  wire [1:0] button,
    output wire       flash_csn,  output wire flash_mosi,
    output wire       flash_wpn,  output wire flash_resetn,
    input  wire       flash_miso,
    output wire       sd_clk,     output wire sd_csn,
    output wire       sd_mosi,
    input  wire       sd_miso,    input wire sd_det,
    output wire       sdram_clk,  output wire sdram_cke,
    output wire       sdram_csn,  output wire sdram_rasn,
    output wire       sdram_casn, output wire sdram_wen,
    output wire [1:0] sdram_ba,   output wire [12:0] sdram_a,
    inout  wire [15:0] sdram_dq,  output wire [1:0] sdram_dqm
);
    assign flash_csn = 1; assign flash_mosi = 0;
    assign flash_wpn = 1; assign flash_resetn = 1;
    assign sd_clk = 0; assign sd_csn = 1; assign sd_mosi = 1;
    assign sdram_clk = 0; assign sdram_cke = 0; assign sdram_csn = 1;
    assign sdram_rasn = 1; assign sdram_casn = 1; assign sdram_wen = 1;
    assign sdram_ba = 0; assign sdram_a = 0; assign sdram_dqm = 2'b11;
    assign sdram_dq = 16'bz;

    localparam integer CLK_HZ      = 25000000;
    localparam integer BAUD         = 115200;
    localparam integer NUM_SENSORS  = 8;
    localparam integer NUM_ZONES    = 4;
    localparam integer RING_STAGES  = 5;
    localparam integer LUTS_PER_ZONE = 500;
    localparam integer MEAS_CYCLES  = CLK_HZ / 2;
    localparam integer SETTLE_CYCLES = CLK_HZ * 30;
    localparam integer NUM_PHASES   = 8;

    logic sys_clk;
    always_ff @(posedge clk) begin
        if (~button[0]) sys_clk <= 0;
        else sys_clk <= ~sys_clk;
    end
    logic [3:0] scc; logic scd;
    always_ff @(posedge sys_clk) begin
        if (~button[0]) begin scc <= 0; scd <= 0; end
        else if (!scd) begin if (scc == 15) scd <= 1; else scc <= scc + 1; end
    end
    wire rst = ~button[0] || !scd;

    logic tx_send; logic [7:0] tx_byte;
    uart_tx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) TX (
        .clk(sys_clk), .send(tx_send), .data(tx_byte), .tx(usb_tx)
    );
    wire rx_v; wire [7:0] rx_d;
    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) RX (
        .clk(sys_clk), .rx(usb_rx), .finish(rx_v), .data(rx_d)
    );
    logic [15:0] tbc;
    wire tbusy = (tbc != 0);
    localparam integer UCC = ((CLK_HZ / BAUD) * 11);
    always_ff @(posedge sys_clk) begin
        if (rst) tbc <= 0;
        else if (tx_send) tbc <= UCC[15:0];
        else if (tbc != 0) tbc <= tbc - 1;
    end

    wire [7:0] dtr_code;
    DTR dtr_inst (.DTROUT(dtr_code));

    wire [NUM_SENSORS-1:0] ring_out;

    genvar si;
    generate for (si = 0; si < NUM_SENSORS; si = si + 1) begin : gen_sensor
        (* keep *) wire [RING_STAGES:0] chain;
        assign chain[0] = chain[RING_STAGES];
        genvar st;
        for (st = 0; st < RING_STAGES; st = st + 1) begin : gen_inv
            (* keep *) LUT4 #(.INIT(16'h5555)) inv (
                .Z(chain[st+1]), .A(chain[st]), .B(1'b0), .C(1'b0), .D(1'b0)
            );
        end
        assign ring_out[si] = chain[1];
    end endgenerate

    logic [23:0] sensor_count [0:NUM_SENSORS-1];
    logic [23:0] sensor_latch [0:NUM_SENSORS-1];
    logic [NUM_SENSORS-1:0] ring_sampled, ring_prev;
    logic clear_counters;

    always_ff @(posedge sys_clk) begin
        ring_sampled <= ring_out;
        ring_prev    <= ring_sampled;
        if (clear_counters) begin
            for (int s = 0; s < NUM_SENSORS; s = s + 1)
                sensor_count[s] <= 0;
        end else if (meas_active) begin
            for (int s = 0; s < NUM_SENSORS; s = s + 1) begin
                if (ring_sampled[s] && !ring_prev[s])
                    sensor_count[s] <= sensor_count[s] + 1;
            end
        end
    end

    logic [NUM_ZONES-1:0] zone_enable;
    logic toggle_bit;
    always_ff @(posedge sys_clk) begin
        if (rst) toggle_bit <= 0;
        else toggle_bit <= ~toggle_bit;
    end

    genvar zi, li;
    generate for (zi = 0; zi < NUM_ZONES; zi = zi + 1) begin : gen_zone
        wire zone_input = toggle_bit & zone_enable[zi];
        (* keep *) wire [LUTS_PER_ZONE-1:0] zone_out;
        for (li = 0; li < LUTS_PER_ZONE; li = li + 1) begin : gen_lut
            (* keep *) LUT4 #(.INIT(16'h6666)) work_lut (
                .Z(zone_out[li]),
                .A(zone_input),
                .B(zone_out[(li > 0) ? li-1 : LUTS_PER_ZONE-1]),
                .C(1'b0),
                .D(1'b0)
            );
        end
    end endgenerate


    logic [3:0]  phase;
    logic [31:0] settle_counter;
    logic [24:0] meas_counter;
    logic        meas_active;
    logic        meas_start;
    logic        meas_done;
    logic [3:0]  report_sensor;
    logic [3:0]  report_state;

    localparam [3:0] ST_SETTLE = 0;
    localparam [3:0] ST_MEAS   = 1;
    localparam [3:0] ST_LATCH  = 2;
    localparam [3:0] ST_REPORT = 3;
    localparam [3:0] ST_NEXT   = 4;
    localparam [3:0] ST_DONE   = 5;

    always_comb begin
        case (phase)
            4'd0: zone_enable = 4'b0000;
            4'd1: zone_enable = 4'b0001;
            4'd2: zone_enable = 4'b0010;
            4'd3: zone_enable = 4'b0100;
            4'd4: zone_enable = 4'b1000;
            4'd5: zone_enable = 4'b0101;
            4'd6: zone_enable = 4'b1010;
            4'd7: zone_enable = 4'b1111;
            default: zone_enable = 4'b0000;
        endcase
    end

    always_ff @(posedge sys_clk) begin
        tx_send        <= 0;
        meas_start     <= 0;
        clear_counters <= 0;

        if (rst) begin
            phase          <= 0;
            settle_counter <= 0;
            meas_counter   <= 0;
            meas_active    <= 0;
            meas_done      <= 0;
            report_sensor  <= 0;
            report_state   <= ST_SETTLE;
            led            <= 5'b00001;
        end else begin
            led[4] <= settle_counter[23];
            case (report_state)
                ST_SETTLE: begin
                    led[3:0] <= phase[3:0];
                    settle_counter <= settle_counter + 1;
                    if (settle_counter >= SETTLE_CYCLES[31:0]) begin
                        settle_counter <= 0;
                        meas_counter   <= 0;
                        meas_active    <= 1;
                        meas_start     <= 1;
                        clear_counters <= 1;
                        report_state <= ST_MEAS;
                    end
                end

                ST_MEAS: begin
                    meas_counter <= meas_counter + 1;
                    if (meas_counter >= MEAS_CYCLES[24:0]) begin
                        meas_active <= 0;
                        for (int s = 0; s < NUM_SENSORS; s = s + 1)
                            sensor_latch[s] <= sensor_count[s];
                        report_sensor <= 0;
                        report_state  <= ST_LATCH;
                    end
                end

                ST_LATCH: begin
                    report_state <= ST_REPORT;
                end

                ST_REPORT: begin
                    if (!tbusy && !tx_send) begin
                        case (report_sensor[3:0])
                            default: begin
                                if (meas_done) begin
                                    report_state <= ST_NEXT;
                                end else begin
                                    tx_byte <= 8'h50;
                                    tx_send <= 1;
                                    report_state <= 4'd6;
                                end
                            end
                        endcase
                    end
                end

                4'd6: if (!tbusy && !tx_send) begin tx_byte <= {4'd0, phase}; tx_send <= 1; report_state <= 4'd7; end
                4'd7: if (!tbusy && !tx_send) begin tx_byte <= {4'd0, report_sensor}; tx_send <= 1; report_state <= 4'd8; end
                4'd8: if (!tbusy && !tx_send) begin tx_byte <= sensor_latch[report_sensor][23:16]; tx_send <= 1; report_state <= 4'd9; end
                4'd9: if (!tbusy && !tx_send) begin tx_byte <= sensor_latch[report_sensor][15:8]; tx_send <= 1; report_state <= 4'd10; end
                4'd10: if (!tbusy && !tx_send) begin tx_byte <= sensor_latch[report_sensor][7:0]; tx_send <= 1; report_state <= 4'd11; end
                4'd11: if (!tbusy && !tx_send) begin tx_byte <= dtr_code; tx_send <= 1; report_state <= 4'd12; end
                4'd12: if (!tbusy && !tx_send) begin
                    tx_byte <= 8'h0A;
                    tx_send <= 1;
                    if (report_sensor == NUM_SENSORS - 1) begin
                        meas_done <= 1;
                        report_state <= ST_NEXT;
                    end else begin
                        report_sensor <= report_sensor + 1;
                        report_state <= ST_REPORT;
                    end
                end

                ST_NEXT: begin
                    meas_done <= 0;
                    if (phase == NUM_PHASES - 1) begin
                        report_state <= ST_DONE;
                        led <= 5'b11111;
                    end else begin
                        phase <= phase + 1;
                        settle_counter <= 0;
                        report_state <= ST_SETTLE;
                    end
                end

                ST_DONE: begin
                    if (rx_v && rx_d == 8'h52) begin
                        phase <= 0;
                        report_state <= ST_SETTLE;
                        settle_counter <= 0;
                        led <= 5'b00001;
                    end
                end
            endcase
        end
    end

endmodule
