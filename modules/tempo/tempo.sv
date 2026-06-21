// TEMPO: Timed Event Measurement and Period Observer
// Frequency counter: counts rising edges of a software-driven signal
// within a configurable gate window. Period mode measures cycles between
// consecutive rising edges. For testing, the signal is register-driven.
//
// Memory map:
//   0x000: SIGNAL    (write) — bit 0 = input signal (software-driven)
//   0x004: GATE      (write) — gate window in sys_clk cycles
//   0x008: FREQ      (read)  — edge count during last completed gate window
//   0x00C: PERIOD    (read)  — sys_clk cycles between last two rising edges
//   0x010: CONTROL   (write) — bit 0 = start gate, bit 1 = reset
//   0x014: STATUS    (read)  — bit 0 = gate active, bit 1 = freq valid, bit 2 = period valid

module tempo (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic        sig_cur, sig_prev;
    logic [31:0] gate_window;
    logic [31:0] gate_counter;
    logic [31:0] edge_count;
    logic [31:0] freq_result;
    logic [31:0] period_counter;
    logic [31:0] period_result;
    logic        gate_active;
    logic        freq_valid;
    logic        period_valid;

    wire rising_edge = sig_cur & ~sig_prev;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            sig_cur        <= 1'b0;
            sig_prev       <= 1'b0;
            gate_window    <= 32'd0;
            gate_counter   <= 32'd0;
            edge_count     <= 32'd0;
            freq_result    <= 32'd0;
            period_counter <= 32'd0;
            period_result  <= 32'd0;
            gate_active    <= 1'b0;
            freq_valid     <= 1'b0;
            period_valid   <= 1'b0;
        end else begin
            sig_prev <= sig_cur;

            // Gate counting
            if (gate_active) begin
                if (rising_edge)
                    edge_count <= edge_count + 32'd1;
                if (gate_counter >= gate_window) begin
                    freq_result <= edge_count + (rising_edge ? 32'd1 : 32'd0);
                    gate_active <= 1'b0;
                    freq_valid  <= 1'b1;
                end
                gate_counter <= gate_counter + 32'd1;
            end

            // Period measurement
            if (rising_edge) begin
                period_result  <= period_counter;
                period_counter <= 32'd0;
                period_valid   <= 1'b1;
            end else begin
                period_counter <= period_counter + 32'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: sig_cur <= reg_wdata[0];
                    3'h1: gate_window <= reg_wdata;
                    3'h4: begin
                        if (reg_wdata[1]) begin
                            edge_count     <= 32'd0;
                            freq_result    <= 32'd0;
                            period_result  <= 32'd0;
                            gate_active    <= 1'b0;
                            freq_valid     <= 1'b0;
                            period_valid   <= 1'b0;
                            period_counter <= 32'd0;
                        end
                        if (reg_wdata[0]) begin
                            gate_counter <= 32'd0;
                            edge_count   <= 32'd0;
                            gate_active  <= 1'b1;
                            freq_valid   <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= {31'd0, sig_cur};
                    3'h1: reg_rdata <= gate_window;
                    3'h2: reg_rdata <= freq_result;
                    3'h3: reg_rdata <= period_result;
                    3'h5: reg_rdata <= {29'd0, period_valid, freq_valid, gate_active};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
