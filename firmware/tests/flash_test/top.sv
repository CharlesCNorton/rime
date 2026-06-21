// flash_test: standalone flash SPI test bitstream.
// Exercises JEDEC-ID read and basic SPI transactions without
// the full rime_service stack. Used for SPI bring-up debugging.

module top (
    input  wire       clk,
    input  wire       usb_rx,
    output wire       usb_tx,
    output logic [4:0] led,
    input  wire [1:0] button,
    output wire       flash_csn,
    output wire       flash_mosi,
    output wire       flash_wpn,
    output wire       flash_resetn,
    input  wire       flash_miso
);
    localparam integer CLK_HZ = 25000000;
    localparam integer BAUD   = 115200;
    localparam integer HALF_DIV = 3;

    wire rst = ~button[0];
    logic sys_clk;

    always_ff @(posedge clk) begin
        if (rst) sys_clk <= 1'b0;
        else     sys_clk <= ~sys_clk;
    end

    logic       rx_finish;
    logic [7:0] rx_data;
    logic       uart_send;
    logic [7:0] uart_data;

    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) RX (
        .clk(sys_clk), .rx(usb_rx), .finish(rx_finish), .data(rx_data)
    );
    uart_tx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) TX (
        .clk(sys_clk), .send(uart_send), .data(uart_data), .tx(usb_tx)
    );

    logic       spi_clk_out;
    logic       spi_csn;
    logic       spi_mosi;
    logic       shift_busy;
    logic       shift_done;
    logic [7:0] shift_rx;
    logic [7:0] shift_tx;
    logic [2:0] shift_bit;
    logic       shift_phase;
    logic [3:0] div_count;
    logic       shift_start;
    logic [7:0] shift_start_byte;

    assign flash_csn    = spi_csn;
    assign flash_mosi   = spi_mosi;
    assign flash_wpn    = 1'b1;
    assign flash_resetn = 1'b1;

    USRMCLK user_flash_clk (
        .USRMCLKI(spi_clk_out),
        .USRMCLKTS(1'b0)
    );

    always_ff @(posedge sys_clk) begin
        shift_done <= 1'b0;
        if (rst) begin
            shift_busy  <= 1'b0;
            shift_rx    <= 8'h00;
            shift_tx    <= 8'h00;
            shift_bit   <= 3'd0;
            shift_phase <= 1'b0;
            div_count   <= 4'd0;
            spi_clk_out <= 1'b0;
            spi_mosi    <= 1'b0;
        end else if (shift_start && !shift_busy) begin
            shift_busy  <= 1'b1;
            shift_rx    <= 8'h00;
            shift_tx    <= shift_start_byte;
            shift_bit   <= 3'd7;
            shift_phase <= 1'b0;
            div_count   <= 4'd0;
            spi_clk_out <= 1'b0;
            spi_mosi    <= shift_start_byte[7];
        end else if (shift_busy) begin
            if (div_count < (HALF_DIV - 1)) begin
                div_count <= div_count + 4'd1;
            end else begin
                div_count <= 4'd0;
                if (!shift_phase) begin
                    spi_clk_out <= 1'b1;
                    shift_phase <= 1'b1;
                    shift_rx[shift_bit] <= flash_miso;
                end else begin
                    spi_clk_out <= 1'b0;
                    shift_phase <= 1'b0;
                    if (shift_bit == 3'd0) begin
                        shift_busy <= 1'b0;
                        shift_done <= 1'b1;
                    end else begin
                        shift_bit <= shift_bit - 3'd1;
                        spi_mosi  <= shift_tx[shift_bit - 3'd1];
                    end
                end
            end
        end
    end

    localparam [3:0] S_IDLE       = 4'd0;
    localparam [3:0] S_CSN_LOW    = 4'd1;
    localparam [3:0] S_SEND_CMD   = 4'd2;
    localparam [3:0] S_WAIT_CMD   = 4'd3;
    localparam [3:0] S_READ_BYTE  = 4'd4;
    localparam [3:0] S_WAIT_READ  = 4'd5;
    localparam [3:0] S_CSN_HIGH   = 4'd6;
    localparam [3:0] S_TX_HEX     = 4'd7;
    localparam [3:0] S_TX_WAIT    = 4'd8;
    localparam [3:0] S_TX_NEWLINE = 4'd9;
    localparam [3:0] S_TX_NL_WAIT = 4'd10;
    localparam [3:0] S_COOLDOWN   = 4'd11;

    logic [3:0]  state;
    logic [23:0] jedec;
    logic [1:0]  read_index;
    logic [3:0]  tx_nibble_index;
    logic [15:0] tx_busy;
    logic [23:0] heartbeat;
    logic        trigger;

    localparam integer UART_CHAR_CLKS = (CLK_HZ / BAUD) * 11;

    function automatic [7:0] hex_char(input [3:0] nibble);
    begin
        hex_char = (nibble < 4'd10) ? (8'h30 + nibble) : (8'h41 + nibble - 4'd10);
    end
    endfunction

    always_ff @(posedge sys_clk) begin
        uart_send   <= 1'b0;
        shift_start <= 1'b0;

        if (rst) begin
            state           <= S_IDLE;
            spi_csn         <= 1'b1;
            jedec           <= 24'h0;
            read_index      <= 2'd0;
            tx_nibble_index <= 4'd0;
            tx_busy         <= 16'd0;
            heartbeat       <= 24'd0;
            trigger         <= 1'b1;
        end else begin
            heartbeat <= heartbeat + 24'd1;

            if (tx_busy != 16'd0)
                tx_busy <= tx_busy - 16'd1;

            if (rx_finish)
                trigger <= 1'b1;

            case (state)
                S_IDLE: begin
                    spi_csn <= 1'b1;
                    if (trigger) begin
                        trigger <= 1'b0;
                        state   <= S_CSN_LOW;
                    end
                end

                S_CSN_LOW: begin
                    spi_csn    <= 1'b0;
                    read_index <= 2'd0;
                    state      <= S_SEND_CMD;
                end

                S_SEND_CMD: begin
                    if (!shift_busy) begin
                        shift_start      <= 1'b1;
                        shift_start_byte <= 8'h9F;
                        state            <= S_WAIT_CMD;
                    end
                end

                S_WAIT_CMD: begin
                    if (shift_done) begin
                        state <= S_READ_BYTE;
                    end
                end

                S_READ_BYTE: begin
                    if (!shift_busy) begin
                        shift_start      <= 1'b1;
                        shift_start_byte <= 8'hFF;
                        state            <= S_WAIT_READ;
                    end
                end

                S_WAIT_READ: begin
                    if (shift_done) begin
                        jedec[23 - (read_index * 8) -: 8] <= shift_rx;
                        if (read_index == 2'd2) begin
                            state <= S_CSN_HIGH;
                        end else begin
                            read_index <= read_index + 2'd1;
                            state      <= S_READ_BYTE;
                        end
                    end
                end

                S_CSN_HIGH: begin
                    spi_csn         <= 1'b1;
                    tx_nibble_index <= 4'd0;
                    state           <= S_TX_HEX;
                end

                S_TX_HEX: begin
                    if (tx_busy == 16'd0) begin
                        uart_send <= 1'b1;
                        case (tx_nibble_index)
                            4'd0: uart_data <= hex_char(jedec[23:20]);
                            4'd1: uart_data <= hex_char(jedec[19:16]);
                            4'd2: uart_data <= 8'h20;
                            4'd3: uart_data <= hex_char(jedec[15:12]);
                            4'd4: uart_data <= hex_char(jedec[11:8]);
                            4'd5: uart_data <= 8'h20;
                            4'd6: uart_data <= hex_char(jedec[7:4]);
                            4'd7: uart_data <= hex_char(jedec[3:0]);
                            default: uart_data <= 8'h3F;
                        endcase
                        tx_busy <= UART_CHAR_CLKS[15:0];
                        if (tx_nibble_index == 4'd7) begin
                            state <= S_TX_WAIT;
                        end else begin
                            tx_nibble_index <= tx_nibble_index + 4'd1;
                        end
                    end
                end

                S_TX_WAIT: begin
                    if (tx_busy == 16'd0)
                        state <= S_TX_NEWLINE;
                end

                S_TX_NEWLINE: begin
                    uart_send <= 1'b1;
                    uart_data <= 8'h0A;
                    tx_busy   <= UART_CHAR_CLKS[15:0];
                    state     <= S_TX_NL_WAIT;
                end

                S_TX_NL_WAIT: begin
                    if (tx_busy == 16'd0)
                        state <= S_COOLDOWN;
                end

                S_COOLDOWN: begin
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

    always_comb begin
        led[0] = heartbeat[23];
        led[1] = (state != S_IDLE);
        led[2] = shift_busy;
        led[3] = (jedec != 24'h0);
        led[4] = ~spi_csn;
    end
endmodule
