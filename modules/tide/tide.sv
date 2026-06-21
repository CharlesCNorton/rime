// TIDE: Direct Digital Synthesis waveform generator
// 32-bit phase accumulator. Outputs 8-bit waveforms: sine, square, saw, triangle.
//
// Memory map:
//   0x000: FREQ    (write) — frequency tuning word (phase increment per tick)
//   0x004: WAVE    (write) — 0=sine, 1=square, 2=saw, 3=triangle
//   0x008: SAMPLE  (read)  — current 8-bit output sample
//   0x00C: PHASE   (r/w)   — current 32-bit phase accumulator
//   0x010: CONTROL (write) — bit 0=enable, bit 1=reset phase

module tide (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] phase;
    logic [31:0] freq;
    logic [1:0]  wave_sel;
    logic        enabled;

    // Quarter-wave sine ROM as a function (survives synthesis optimization)
    function automatic [7:0] sine_quarter(input [5:0] idx);
        case (idx)
            6'd0:  sine_quarter=8'd0;   6'd1:  sine_quarter=8'd3;
            6'd2:  sine_quarter=8'd6;   6'd3:  sine_quarter=8'd9;
            6'd4:  sine_quarter=8'd12;  6'd5:  sine_quarter=8'd16;
            6'd6:  sine_quarter=8'd19;  6'd7:  sine_quarter=8'd22;
            6'd8:  sine_quarter=8'd25;  6'd9:  sine_quarter=8'd28;
            6'd10: sine_quarter=8'd31;  6'd11: sine_quarter=8'd34;
            6'd12: sine_quarter=8'd37;  6'd13: sine_quarter=8'd40;
            6'd14: sine_quarter=8'd43;  6'd15: sine_quarter=8'd46;
            6'd16: sine_quarter=8'd49;  6'd17: sine_quarter=8'd51;
            6'd18: sine_quarter=8'd54;  6'd19: sine_quarter=8'd57;
            6'd20: sine_quarter=8'd60;  6'd21: sine_quarter=8'd63;
            6'd22: sine_quarter=8'd65;  6'd23: sine_quarter=8'd68;
            6'd24: sine_quarter=8'd71;  6'd25: sine_quarter=8'd73;
            6'd26: sine_quarter=8'd76;  6'd27: sine_quarter=8'd78;
            6'd28: sine_quarter=8'd81;  6'd29: sine_quarter=8'd83;
            6'd30: sine_quarter=8'd85;  6'd31: sine_quarter=8'd88;
            6'd32: sine_quarter=8'd90;  6'd33: sine_quarter=8'd92;
            6'd34: sine_quarter=8'd94;  6'd35: sine_quarter=8'd96;
            6'd36: sine_quarter=8'd98;  6'd37: sine_quarter=8'd100;
            6'd38: sine_quarter=8'd102; 6'd39: sine_quarter=8'd104;
            6'd40: sine_quarter=8'd106; 6'd41: sine_quarter=8'd107;
            6'd42: sine_quarter=8'd109; 6'd43: sine_quarter=8'd111;
            6'd44: sine_quarter=8'd112; 6'd45: sine_quarter=8'd113;
            6'd46: sine_quarter=8'd115; 6'd47: sine_quarter=8'd116;
            6'd48: sine_quarter=8'd117; 6'd49: sine_quarter=8'd118;
            6'd50: sine_quarter=8'd119; 6'd51: sine_quarter=8'd120;
            6'd52: sine_quarter=8'd121; 6'd53: sine_quarter=8'd122;
            6'd54: sine_quarter=8'd123; 6'd55: sine_quarter=8'd123;
            6'd56: sine_quarter=8'd124; 6'd57: sine_quarter=8'd124;
            6'd58: sine_quarter=8'd125; 6'd59: sine_quarter=8'd125;
            6'd60: sine_quarter=8'd126; 6'd61: sine_quarter=8'd126;
            6'd62: sine_quarter=8'd126; 6'd63: sine_quarter=8'd127;
        endcase
    endfunction

    // Full sine from quarter-wave symmetry
    wire [5:0] q_idx = phase[29] ? ~phase[28:23] : phase[28:23];
    wire [7:0] q_val = sine_quarter(q_idx);
    wire [7:0] sine_out = phase[30] ? (8'd128 - q_val) : (8'd128 + q_val);

    wire [7:0] square_out = phase[31] ? 8'd255 : 8'd0;
    wire [7:0] saw_out = phase[31:24];
    wire [7:0] tri_out = phase[31] ? ~phase[30:23] : phase[30:23];

    wire [7:0] sample = (wave_sel == 2'd0) ? sine_out :
                         (wave_sel == 2'd1) ? square_out :
                         (wave_sel == 2'd2) ? saw_out : tri_out;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            phase <= 32'd0; freq <= 32'd0;
            wave_sel <= 2'd0; enabled <= 1'b0;
        end else begin
            if (enabled) phase <= phase + freq;

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: freq <= reg_wdata;
                    3'h1: wave_sel <= reg_wdata[1:0];
                    3'h3: phase <= reg_wdata;
                    3'h4: begin
                        enabled <= reg_wdata[0];
                        if (reg_wdata[1]) phase <= 32'd0;
                    end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: reg_rdata <= {24'd0, sample};
                    3'h3: reg_rdata <= phase;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
