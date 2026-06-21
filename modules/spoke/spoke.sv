// SPOKE: General-purpose SPI master with software-driven slave
// 8-bit shift register, configurable clock divider, CS control.
// For testing, MISO loops back from the LSB of the loopback register
// (CPU writes a value to simulate slave responses).
//
// Memory map:
//   0x000: TX_DATA  (write) — 8-bit byte to send, triggers transaction
//   0x004: RX_DATA  (read)  — 8-bit byte received from slave
//   0x008: STATUS   (read)  — bit 0 = busy, bit 1 = done
//   0x00C: CONTROL  (write) — bit 0 = CS_low (assert), bit 1 = reset
//   0x010: DIV      (write) — 16-bit clock divider
//   0x014: LOOPBACK (write) — 8-bit value the simulated slave returns
//   0x018: CS_OUT   (read)  — current CS output state
//   0x01C: CLK_CNT  (read)  — debug bit count

module spoke (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0] tx_shift, rx_shift;
    logic [3:0] bit_count;
    logic       busy;
    logic       done;
    logic       cs_n;
    logic [15:0] div_count;
    logic [15:0] div_reload;
    logic [7:0]  loopback;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            tx_shift   <= 8'd0;
            rx_shift   <= 8'd0;
            bit_count  <= 4'd0;
            busy       <= 1'b0;
            done       <= 1'b0;
            cs_n       <= 1'b1;
            div_count  <= 16'd0;
            div_reload <= 16'd4;
            loopback   <= 8'd0;
        end else begin
            if (busy) begin
                if (div_count == 16'd0) begin
                    div_count <= div_reload;
                    rx_shift  <= {rx_shift[6:0], loopback[bit_count[2:0]]};
                    tx_shift  <= {tx_shift[6:0], 1'b0};
                    if (bit_count == 4'd7) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                    end
                    bit_count <= bit_count + 4'd1;
                end else begin
                    div_count <= div_count - 16'd1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin
                        tx_shift  <= reg_wdata[7:0];
                        rx_shift  <= 8'd0;
                        bit_count <= 4'd0;
                        div_count <= div_reload;
                        busy      <= 1'b1;
                        done      <= 1'b0;
                    end
                    3'h3: begin
                        if (reg_wdata[1]) begin
                            busy <= 1'b0; done <= 1'b0;
                        end
                        cs_n <= ~reg_wdata[0];
                    end
                    3'h4: div_reload <= reg_wdata[15:0];
                    3'h5: loopback   <= reg_wdata[7:0];
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {24'd0, rx_shift};
                    3'h2: reg_rdata <= {30'd0, done, busy};
                    3'h6: reg_rdata <= {31'd0, cs_n};
                    3'h7: reg_rdata <= {28'd0, bit_count};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
