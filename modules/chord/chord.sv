// CHORD: 4-voice DDS synthesizer with waveform selection
// Each voice has: frequency (phase increment), amplitude (0-255),
// and waveform select (0=square, 1=saw, 2=triangle, 3=sine).
// Voices are mixed (summed and saturated) into an 8-bit output.
//
// Sine uses a 64-entry quarter-wave LUT with symmetry expansion,
// identical to the TIDE module's proven implementation.
//
// Memory map:
//   0x000: V0_FREQ (write) — voice 0 frequency tuning word (32-bit phase increment)
//   0x004: V0_AMP  (write) — voice 0 amplitude (0-255)
//   0x008: V1_FREQ (write)
//   0x00C: V1_AMP  (write)
//   0x010: V2_FREQ (write)
//   0x014: V2_AMP  (write)
//   0x018: V3_FREQ (write)
//   0x01C: V3_AMP  (write)
//   0x020: SAMPLE  (read)  — mixed 8-bit output
//   0x024: CONTROL (write) — bit 0=enable, bit 1=reset phases
//   0x028: V0_WAVE (write) — voice 0 waveform: 0=square, 1=saw, 2=tri, 3=sine
//   0x02C: V1_WAVE (write)
//   0x030: V2_WAVE (write)
//   0x034: V3_WAVE (write)

module chord (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] freq [0:3];
    logic [7:0]  amp  [0:3];
    logic [1:0]  wave [0:3];
    logic [31:0] phase [0:3];
    logic        enabled;

    // Quarter-wave sine LUT (64 entries, 0-127 range)
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

    // Per-voice waveform generation
    function automatic [7:0] voice_sample(input [31:0] ph, input [1:0] wv, input [7:0] a);
        logic [7:0] raw;
        logic [5:0] q_idx;
        logic [7:0] q_val;
        case (wv)
            2'd0: raw = ph[31] ? 8'd255 : 8'd0;                           // square
            2'd1: raw = ph[31:24];                                          // sawtooth
            2'd2: raw = ph[31] ? ~ph[30:23] : ph[30:23];                   // triangle
            2'd3: begin                                                      // sine
                q_idx = ph[29] ? ~ph[28:23] : ph[28:23];
                q_val = sine_quarter(q_idx);
                raw = ph[30] ? (8'd128 - q_val) : (8'd128 + q_val);
            end
        endcase
        // Scale by amplitude: (raw * amp) >> 8
        // For square: output is 0 or amp (legacy behaviour preserved when amp < 255)
        if (wv == 2'd0)
            voice_sample = ph[31] ? a : 8'd0;
        else begin
            logic [15:0] scaled;
            scaled = raw * a;
            voice_sample = scaled[15:8];
        end
    endfunction

    wire [7:0] v0 = voice_sample(phase[0], wave[0], amp[0]);
    wire [7:0] v1 = voice_sample(phase[1], wave[1], amp[1]);
    wire [7:0] v2 = voice_sample(phase[2], wave[2], amp[2]);
    wire [7:0] v3 = voice_sample(phase[3], wave[3], amp[3]);

    // Mix with saturation
    wire [9:0] mix = {2'd0, v0} + {2'd0, v1} + {2'd0, v2} + {2'd0, v3};
    wire [7:0] sample = (mix > 10'd255) ? 8'd255 : mix[7:0];

    integer _i;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            enabled <= 1'b0;
            for (_i = 0; _i < 4; _i = _i + 1) begin
                freq[_i] <= 32'd0; amp[_i] <= 8'd0;
                phase[_i] <= 32'd0; wave[_i] <= 2'd0;
            end
        end else begin
            if (enabled)
                for (_i = 0; _i < 4; _i = _i + 1)
                    phase[_i] <= phase[_i] + freq[_i];

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: freq[0] <= reg_wdata;
                    4'h1: amp[0]  <= reg_wdata[7:0];
                    4'h2: freq[1] <= reg_wdata;
                    4'h3: amp[1]  <= reg_wdata[7:0];
                    4'h4: freq[2] <= reg_wdata;
                    4'h5: amp[2]  <= reg_wdata[7:0];
                    4'h6: freq[3] <= reg_wdata;
                    4'h7: amp[3]  <= reg_wdata[7:0];
                    4'h9: begin
                        enabled <= reg_wdata[0];
                        if (reg_wdata[1])
                            for (_i = 0; _i < 4; _i = _i + 1)
                                phase[_i] <= 32'd0;
                    end
                    4'hA: wave[0] <= reg_wdata[1:0];
                    4'hB: wave[1] <= reg_wdata[1:0];
                    4'hC: wave[2] <= reg_wdata[1:0];
                    4'hD: wave[3] <= reg_wdata[1:0];
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h8: reg_rdata <= {24'd0, sample};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
