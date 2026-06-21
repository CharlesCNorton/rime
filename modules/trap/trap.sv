// TRAP: Triggered Response to Address Predicate
// 4-address hardware breakpoint/watchpoint. Compares bus addresses
// against programmed match values. Fires a flag when a match is seen.
// Requires snoop interface for passive bus observation.
//
// Memory map:
//   0x000: MATCH0  (write) — 32-bit match address 0
//   0x004: MATCH1  (write) — 32-bit match address 1
//   0x008: MATCH2  (write) — 32-bit match address 2
//   0x00C: MATCH3  (write) — 32-bit match address 3
//   0x010: ENABLE  (write) — bits [3:0] = per-breakpoint enable
//   0x014: FLAGS   (read)  — bits [3:0] = which breakpoints fired (sticky, clear on read)
//   0x018: LAST    (read)  — address of last match
//   0x01C: COUNT   (read)  — total match count since last reset
//   0x020: CONTROL (write) — bit 0 = reset flags/count

module trap (
    input  wire        clk,
    input  wire        rst,

    input  wire [31:0] snoop_addr,
    input  wire [3:0]  snoop_wstrb,
    input  wire        snoop_valid,
    input  wire        snoop_ready,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] match_addr [0:3];
    logic [3:0]  enable;
    logic [3:0]  flags;
    logic [31:0] last_match;
    logic [31:0] match_count;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            enable      <= 4'd0;
            flags       <= 4'd0;
            last_match  <= 32'd0;
            match_count <= 32'd0;
            for (integer i = 0; i < 4; i = i + 1)
                match_addr[i] <= 32'd0;
        end else begin
            // Passive snoop: check for matches
            if (snoop_valid && snoop_ready) begin
                for (integer i = 0; i < 4; i = i + 1) begin
                    if (enable[i] && snoop_addr == match_addr[i]) begin
                        flags[i]    <= 1'b1;
                        last_match  <= snoop_addr;
                        match_count <= match_count + 32'd1;
                    end
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: match_addr[0] <= reg_wdata;
                    4'h1: match_addr[1] <= reg_wdata;
                    4'h2: match_addr[2] <= reg_wdata;
                    4'h3: match_addr[3] <= reg_wdata;
                    4'h4: enable <= reg_wdata[3:0];
                    4'h8: begin
                        if (reg_wdata[0]) begin
                            flags       <= 4'd0;
                            match_count <= 32'd0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: reg_rdata <= match_addr[0];
                    4'h1: reg_rdata <= match_addr[1];
                    4'h2: reg_rdata <= match_addr[2];
                    4'h3: reg_rdata <= match_addr[3];
                    4'h4: reg_rdata <= {28'd0, enable};
                    4'h5: begin
                        reg_rdata <= {28'd0, flags};
                        flags     <= 4'd0;
                    end
                    4'h6: reg_rdata <= last_match;
                    4'h7: reg_rdata <= match_count;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
