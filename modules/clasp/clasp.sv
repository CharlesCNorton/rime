// CLASP: Contested Lock with Atomic Set Protocol
// 8-slot hardware mutex array. Each slot is a single bit.
// ACQUIRE returns the previous value: 0 means lock was free and now held;
// 1 means lock was already held (request denied).
// RELEASE clears the slot.
//
// Memory map:
//   0x000-0x01C: ACQUIRE[0..7] (read)  — atomic test-and-set, returns prior value
//   0x020-0x03C: RELEASE[0..7] (write) — clear the slot (any data)
//   0x040:       STATE          (read)  — current 8-bit state of all slots
//   0x044:       CONTROL        (write) — bit 0 = clear all
//   0x048:       OWNERS         (read)  — same as STATE (alias)

module clasp (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [7:0] state;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            state <= 8'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6:5] == 2'b01) begin
                    // RELEASE[i] at offset 0x020 + i*4
                    state[reg_addr[4:2]] <= 1'b0;
                end else if (reg_addr[6:2] == 5'h11) begin
                    // CONTROL at 0x044
                    if (reg_wdata[0]) state <= 8'd0;
                end
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[6:5] == 2'b00) begin
                    // ACQUIRE[i] at offset 0x000 + i*4 — atomic test-and-set
                    reg_rdata <= {31'd0, state[reg_addr[4:2]]};
                    state[reg_addr[4:2]] <= 1'b1;
                end else if (reg_addr[6:2] == 5'h10) begin
                    // STATE at 0x040
                    reg_rdata <= {24'd0, state};
                end else if (reg_addr[6:2] == 5'h12) begin
                    // OWNERS at 0x048
                    reg_rdata <= {24'd0, state};
                end else begin
                    reg_rdata <= 32'd0;
                end
            end
        end
    end
endmodule
