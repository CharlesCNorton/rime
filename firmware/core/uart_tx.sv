// uart_tx: asynchronous UART transmitter.
//
// 8N1 serial transmitter. Drives tx high (idle) until send is pulsed,
// then shifts out one start bit, BITS data bits LSB-first, and one stop bit.
//
// Interface:
//   clk  — system clock
//   send — pulse high for one cycle to begin transmission; data must be stable
//   data — byte to transmit, latched on the cycle send is asserted
//   tx   — serial output line (idles high)
//
// Parameters:
//   CLK       — system clock frequency in Hz
//   BAUD_RATE — target baud rate (default 115200)
//   BITS      — data bits per frame (default 8)
//
// The caller must not assert send while a transmission is in progress.
// The top-level tx_busy counter in top.sv enforces this at the system level.

module uart_tx #(
	parameter CLK = 50000000,
	parameter BAUD_RATE = 115200,
	parameter BITS = 8
) (
	input                   clk,
	input                   send,
	input        [BITS-1:0] data,
	output logic            tx
);
	localparam CLK_DIVISOR = CLK / BAUD_RATE;

	logic [$clog2(CLK_DIVISOR):0] clkd;
	logic [$clog2(BITS)-1:0]      index;

	enum {IDLE, START, TRANSMISSION, STOP} state;

	initial begin
		tx = 1'b1;
		clkd = 0;
		index = 0;
		state = IDLE;
	end

	always @(posedge clk) begin
		case (state)
		IDLE: begin
			tx <= 1'b1;   // line idles high
			clkd <= 0;
			index <= 0;

			if (send) begin
				state <= START;
			end
		end
		START: begin
			tx <= 1'b0;   // start bit: drive low for one bit period

			if (clkd < CLK_DIVISOR-1) begin
				clkd <= clkd + 1;
			end else begin
				clkd <= 0;
				state <= TRANSMISSION;
			end
		end
		TRANSMISSION: begin
			tx <= data[index];

			if (clkd < CLK_DIVISOR-1) begin
				clkd <= clkd + 1;
			end else begin
				clkd <= 0;

				if (index < (BITS-1)) begin
					index <= index + 1;
				end else begin
					index <= 0;
					state <= STOP;
				end
			end
		end
		STOP: begin
			tx <= 1'b1;   // stop bit: drive high for one bit period

			if (clkd < CLK_DIVISOR-1) begin
				clkd <= clkd + 1;
			end else begin
				clkd <= 0;
				state <= IDLE;
			end
		end
		endcase
	end
endmodule
