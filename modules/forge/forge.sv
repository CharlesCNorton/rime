// FORGE: 64-round iterative compression using SHA-256 primitives
// One round per cycle.  Uses the correct FIPS 197 initial hash values,
// round constants, Ch/Maj/Σ0/Σ1 functions, and working-variable update.
// The message schedule is simplified: a single 32-bit input word is used
// for every round (standard SHA-256 expands 16 input words to 64 via
// σ0/σ1).  Output is therefore NOT a standard SHA-256 digest.
//
// Memory map:
//   0x000: DATA    (write) — 32-bit input word
//   0x004: CONTROL (write) — bit 0 = compute hash
//   0x008: STATUS  (read)  — bit 0 = done
//   0x00C: H0      (read)  — hash word 0
//   0x010: H1      (read)  — hash word 1
//   0x014: H2      (read)  — hash word 2
//   0x018: H3      (read)  — hash word 3

module forge (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] data_in;
    logic [31:0] h [0:7];
    logic        done;
    logic        computing;
    logic [5:0]  round;

    localparam [31:0] H0_INIT = 32'h6a09e667;
    localparam [31:0] H1_INIT = 32'hbb67ae85;
    localparam [31:0] H2_INIT = 32'h3c6ef372;
    localparam [31:0] H3_INIT = 32'ha54ff53a;
    localparam [31:0] H4_INIT = 32'h510e527f;
    localparam [31:0] H5_INIT = 32'h9b05688c;
    localparam [31:0] H6_INIT = 32'h1f83d9ab;
    localparam [31:0] H7_INIT = 32'h5be0cd19;

    // All 64 SHA-256 round constants
    function automatic [31:0] get_k(input [5:0] r);
        case (r)
            6'd0:  get_k=32'h428a2f98; 6'd1:  get_k=32'h71374491;
            6'd2:  get_k=32'hb5c0fbcf; 6'd3:  get_k=32'he9b5dba5;
            6'd4:  get_k=32'h3956c25b; 6'd5:  get_k=32'h59f111f1;
            6'd6:  get_k=32'h923f82a4; 6'd7:  get_k=32'hab1c5ed5;
            6'd8:  get_k=32'hd807aa98; 6'd9:  get_k=32'h12835b01;
            6'd10: get_k=32'h243185be; 6'd11: get_k=32'h550c7dc3;
            6'd12: get_k=32'h72be5d74; 6'd13: get_k=32'h80deb1fe;
            6'd14: get_k=32'h9bdc06a7; 6'd15: get_k=32'hc19bf174;
            6'd16: get_k=32'he49b69c1; 6'd17: get_k=32'hefbe4786;
            6'd18: get_k=32'h0fc19dc6; 6'd19: get_k=32'h240ca1cc;
            6'd20: get_k=32'h2de92c6f; 6'd21: get_k=32'h4a7484aa;
            6'd22: get_k=32'h5cb0a9dc; 6'd23: get_k=32'h76f988da;
            6'd24: get_k=32'h983e5152; 6'd25: get_k=32'ha831c66d;
            6'd26: get_k=32'hb00327c8; 6'd27: get_k=32'hbf597fc7;
            6'd28: get_k=32'hc6e00bf3; 6'd29: get_k=32'hd5a79147;
            6'd30: get_k=32'h06ca6351; 6'd31: get_k=32'h14292967;
            6'd32: get_k=32'h27b70a85; 6'd33: get_k=32'h2e1b2138;
            6'd34: get_k=32'h4d2c6dfc; 6'd35: get_k=32'h53380d13;
            6'd36: get_k=32'h650a7354; 6'd37: get_k=32'h766a0abb;
            6'd38: get_k=32'h81c2c92e; 6'd39: get_k=32'h92722c85;
            6'd40: get_k=32'ha2bfe8a1; 6'd41: get_k=32'ha81a664b;
            6'd42: get_k=32'hc24b8b70; 6'd43: get_k=32'hc76c51a3;
            6'd44: get_k=32'hd192e819; 6'd45: get_k=32'hd6990624;
            6'd46: get_k=32'hf40e3585; 6'd47: get_k=32'h106aa070;
            6'd48: get_k=32'h19a4c116; 6'd49: get_k=32'h1e376c08;
            6'd50: get_k=32'h2748774c; 6'd51: get_k=32'h34b0bcb5;
            6'd52: get_k=32'h391c0cb3; 6'd53: get_k=32'h4ed8aa4a;
            6'd54: get_k=32'h5b9cca4f; 6'd55: get_k=32'h682e6ff3;
            6'd56: get_k=32'h748f82ee; 6'd57: get_k=32'h78a5636f;
            6'd58: get_k=32'h84c87814; 6'd59: get_k=32'h8cc70208;
            6'd60: get_k=32'h90befffa; 6'd61: get_k=32'ha4506ceb;
            6'd62: get_k=32'hbef9a3f7; 6'd63: get_k=32'hc67178f2;
        endcase
    endfunction

    // SHA-256 auxiliary functions (FIPS 180-4 Section 4.1.2)
    function automatic [31:0] ch(input [31:0] e, f, g);
        ch = (e & f) ^ (~e & g);  // Choice: each bit selects f or g based on e
    endfunction

    function automatic [31:0] maj(input [31:0] a, b, c);
        maj = (a & b) ^ (a & c) ^ (b & c);  // Majority: output is the majority vote
    endfunction

    function automatic [31:0] bsig0(input [31:0] x);
        bsig0 = {x[1:0],x[31:2]} ^ {x[12:0],x[31:13]} ^ {x[21:0],x[31:22]};  // Σ0: ROTR2 ^ ROTR13 ^ ROTR22
    endfunction

    function automatic [31:0] bsig1(input [31:0] x);
        bsig1 = {x[5:0],x[31:6]} ^ {x[10:0],x[31:11]} ^ {x[24:0],x[31:25]};  // Σ1: ROTR6 ^ ROTR11 ^ ROTR25
    endfunction

    wire [31:0] cur_k = get_k(round);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            done <= 1'b0; computing <= 1'b0; round <= 6'd0;
            h[0]<=H0_INIT; h[1]<=H1_INIT; h[2]<=H2_INIT; h[3]<=H3_INIT;
            h[4]<=H4_INIT; h[5]<=H5_INIT; h[6]<=H6_INIT; h[7]<=H7_INIT;
        end else begin
            if (computing) begin
                // One SHA-256 compression round per cycle.
                // Working variables shift down: a←new, b←a, c←b, ...
                // T1 = h + Σ1(e) + Ch(e,f,g) + K[round] + W[round]
                // T2 = Σ0(a) + Maj(a,b,c)
                // Here W[round] is always data_in (simplified schedule).
                h[7] <= h[6]; h[6] <= h[5]; h[5] <= h[4];
                h[4] <= h[3] + h[7] + bsig1(h[4]) + ch(h[4],h[5],h[6]) + cur_k + data_in;  // d + T1
                h[3] <= h[2]; h[2] <= h[1]; h[1] <= h[0];
                h[0] <= h[7] + bsig1(h[4]) + ch(h[4],h[5],h[6]) + cur_k + data_in + bsig0(h[0]) + maj(h[0],h[1],h[2]);  // T1 + T2

                if (round == 6'd63) begin
                    computing <= 1'b0;
                    done <= 1'b1;
                end
                round <= round + 6'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: data_in <= reg_wdata;
                    3'h1: begin
                        if (reg_wdata[0]) begin
                            computing <= 1'b1;
                            done <= 1'b0;
                            round <= 6'd0;
                            h[0]<=H0_INIT; h[1]<=H1_INIT; h[2]<=H2_INIT; h[3]<=H3_INIT;
                            h[4]<=H4_INIT; h[5]<=H5_INIT; h[6]<=H6_INIT; h[7]<=H7_INIT;
                        end
                    end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: reg_rdata <= {31'd0, done};
                    3'h3: reg_rdata <= h[0];
                    3'h4: reg_rdata <= h[1];
                    3'h5: reg_rdata <= h[2];
                    3'h6: reg_rdata <= h[3];
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
