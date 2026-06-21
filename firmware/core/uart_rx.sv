// uart_rx: asynchronous UART receiver.
//
// 8N1 serial receiver with mid-bit sampling. Active-low start-bit
// detection, LSB-first data capture, one stop bit.
//
// Interface:
//   clk    — system clock
//   rx     — serial input line (active-low idle)
//   finish — one-cycle pulse when a complete byte has been received
//   data   — captured byte, valid on the cycle finish is asserted
//
// Parameters:
//   CLK       — system clock frequency in Hz
//   BAUD_RATE — target baud rate (default 115200)
//   BITS      — data bits per frame (default 8)
//
// Sampling: the START state waits half a bit period from the falling
// edge of the start bit, centering subsequent samples in the middle
// of each data bit. This tolerates up to ~4% baud-rate mismatch.

module uart_rx #(
	parameter CLK = 50000000,
	parameter BAUD_RATE = 115200,
	parameter BITS = 8
) (
	input                   clk,
	input                   rx,
	output logic            finish,
	output logic [BITS-1:0] data
);
	localparam CLK_DIVISOR = CLK / BAUD_RATE;

	logic [$clog2(CLK_DIVISOR):0] clkd;
	logic [$clog2(BITS)-1:0]      index;

	enum {IDLE, START, TRANSMISSION, STOP} state;

	initial begin
		finish = 1'b0;
		data = 0;
		clkd = 0;
		index = 0;
		state = IDLE;
	end

	always @(posedge clk) begin
		finish <= 1'b0;

		case (state)
		IDLE: begin
			clkd <= 0;
			index <= 0;
			// Falling edge on rx: potential start bit
			if (rx == 1'b0) begin
				state <= START;
			end
		end
		START: begin
			// Wait half a bit period to sample at the center of the start bit
			if (clkd == (CLK_DIVISOR-1)/2) begin
				clkd <= 0;
				// Confirm rx is still low (reject glitches)
				if (rx == 1'b0) begin
					state <= TRANSMISSION;
				end else begin
					state <= IDLE;
				end
			end else begin
				clkd <= clkd + 1;
			end
		end
		TRANSMISSION: begin
			// Wait one full bit period then sample
			if (clkd < CLK_DIVISOR-1) begin
				clkd <= clkd + 1;
			end else begin
				clkd <= 0;
				data[index] <= rx;

				if (index < (BITS-1)) begin
					index <= index + 1;
				end else begin
					index <= 0;
					state <= STOP;
				end
			end
		end
		STOP: begin
			// Wait one bit period for the stop bit then return to idle
			if (clkd < CLK_DIVISOR-1) begin
				clkd <= clkd + 1;
			end else begin
				clkd <= 0;
				finish <= 1'b1;
				state <= IDLE;
			end
		end
		endcase
	end
endmodule
