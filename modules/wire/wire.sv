// WIRE: I2C master FSM
// Software writes commands; FSM steps through start/byte/ack/stop sequences.
// For testing, the simulated slave always ACKs and returns the loopback value.
//
// Memory map:
//   0x000: ADDR     (write) — 7-bit slave address, bit 7 = R/W direction
//   0x004: TX_DATA  (write) — data byte to send
//   0x008: RX_DATA  (read)  — data byte received
//   0x00C: CONTROL  (write) — bit 0 = start tx, bit 1 = start rx, bit 2 = reset, bit 3 = stop
//   0x010: STATUS   (read)  — bit 0 = busy, bit 1 = done, bit 2 = nack
//   0x014: LOOPBACK (write) — value the simulated slave returns on read
//   0x018: STATE    (read)  — current FSM state (debug)

module wire_mod (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // I2C transaction FSM. The simulated slave always ACKs and returns
    // the loopback register value on reads. No external SDA/SCL pins —
    // this module exercises the bus protocol in software simulation only.
    typedef enum logic [3:0] {
        S_IDLE, S_START, S_ADDR, S_ADDR_ACK,
        S_TX, S_TX_ACK, S_RX, S_RX_ACK, S_STOP, S_DONE
    } state_t;

    state_t state;
    logic [7:0] addr_reg, tx_reg, rx_reg, loopback;
    logic [3:0] bit_idx;
    logic       busy, done, nack;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            state    <= S_IDLE;
            addr_reg <= 8'd0;
            tx_reg   <= 8'd0;
            rx_reg   <= 8'd0;
            loopback <= 8'd0;
            bit_idx  <= 4'd0;
            busy     <= 1'b0;
            done     <= 1'b0;
            nack     <= 1'b0;
        end else begin
            case (state)
                S_IDLE: ;
                S_START: state <= S_ADDR;
                S_ADDR: begin
                    if (bit_idx == 4'd7) begin
                        state <= S_ADDR_ACK;
                        bit_idx <= 4'd0;
                    end else begin
                        bit_idx <= bit_idx + 4'd1;
                    end
                end
                S_ADDR_ACK: begin
                    // Simulated slave always ACKs
                    if (addr_reg[0]) state <= S_RX;
                    else state <= S_TX;
                end
                S_TX: begin
                    if (bit_idx == 4'd7) begin
                        state <= S_TX_ACK;
                        bit_idx <= 4'd0;
                    end else begin
                        bit_idx <= bit_idx + 4'd1;
                    end
                end
                S_TX_ACK: state <= S_STOP;
                S_RX: begin
                    if (bit_idx == 4'd7) begin
                        rx_reg <= loopback;
                        state <= S_RX_ACK;
                        bit_idx <= 4'd0;
                    end else begin
                        bit_idx <= bit_idx + 4'd1;
                    end
                end
                S_RX_ACK: state <= S_STOP;
                S_STOP: state <= S_DONE;
                S_DONE: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                end
                default: state <= S_IDLE;
            endcase

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: addr_reg <= reg_wdata[7:0];
                    3'h1: tx_reg   <= reg_wdata[7:0];
                    3'h3: begin
                        if (reg_wdata[2]) begin
                            state <= S_IDLE;
                            busy <= 1'b0; done <= 1'b0; nack <= 1'b0;
                        end
                        if (reg_wdata[0]) begin
                            state <= S_START;
                            busy <= 1'b1; done <= 1'b0; nack <= 1'b0;
                            bit_idx <= 4'd0;
                        end
                        if (reg_wdata[1]) begin
                            addr_reg[0] <= 1'b1;
                            state <= S_START;
                            busy <= 1'b1; done <= 1'b0;
                            bit_idx <= 4'd0;
                        end
                    end
                    3'h5: loopback <= reg_wdata[7:0];
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: reg_rdata <= {24'd0, rx_reg};
                    3'h4: reg_rdata <= {29'd0, nack, done, busy};
                    3'h6: reg_rdata <= {28'd0, state};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
