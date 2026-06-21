// AXIOM: Hardware JSON token scanner
// Feed bytes, get token type classification.
// Tracks nesting depth for objects/arrays.
//
// Memory map:
//   0x000: INPUT  (write) — feed one byte
//   0x004: TOKEN  (read)  — last token type:
//          0=none, 1=lbrace, 2=rbrace, 3=lbracket, 4=rbracket,
//          5=colon, 6=comma, 7=string_start, 8=string_end,
//          9=digit, 10=whitespace, 11=true/false/null keyword char
//   0x008: DEPTH  (read)  — nesting depth (object+array)
//   0x00C: CONTROL (write) — bit 0 = reset
//   0x010: OFFSET (read)  — byte offset since reset
//   0x014: ERRORS (read)  — count of unexpected tokens (unmatched braces etc)

module axiom (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [3:0]  token;
    logic [7:0]  depth;
    logic [31:0] offset;
    logic [31:0] errors;
    logic        in_string;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            token <= 4'd0; depth <= 8'd0; offset <= 32'd0;
            errors <= 32'd0; in_string <= 1'b0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin // INPUT
                        offset <= offset + 32'd1;
                        if (in_string) begin
                            if (reg_wdata[7:0] == 8'h22) begin // closing "
                                token <= 4'd8; // string_end
                                in_string <= 1'b0;
                            end else
                                token <= 4'd7; // string content
                        end else begin
                            case (reg_wdata[7:0])
                                8'h7B: begin token<=4'd1; depth<=depth+1; end  // {
                                8'h7D: begin token<=4'd2;                       // }
                                    if (depth > 0) depth<=depth-1;
                                    else errors<=errors+1;
                                end
                                8'h5B: begin token<=4'd3; depth<=depth+1; end  // [
                                8'h5D: begin token<=4'd4;                       // ]
                                    if (depth > 0) depth<=depth-1;
                                    else errors<=errors+1;
                                end
                                8'h3A: token <= 4'd5;  // :
                                8'h2C: token <= 4'd6;  // ,
                                8'h22: begin token<=4'd7; in_string<=1'b1; end // opening "
                                8'h20, 8'h09, 8'h0A, 8'h0D: token <= 4'd10; // whitespace
                                default: begin
                                    if (reg_wdata[7:0] >= 8'h30 && reg_wdata[7:0] <= 8'h39)
                                        token <= 4'd9;  // digit
                                    else
                                        token <= 4'd11; // keyword char (t/f/n)
                                end
                            endcase
                        end
                    end
                    3'h3: begin
                        if (reg_wdata[0]) begin
                            token<=0; depth<=0; offset<=0; errors<=0; in_string<=0;
                        end
                    end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h1: reg_rdata <= {28'd0, token};
                    3'h2: reg_rdata <= {24'd0, depth};
                    3'h4: reg_rdata <= offset;
                    3'h5: reg_rdata <= errors;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
