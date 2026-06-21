// ANVIL: Hardware CRC-32 accelerator
// IEEE 802.3 polynomial 0x04C11DB7 (reflected: 0xEDB88320).
// Feed bytes one at a time, read the running CRC at any point.
// Single-cycle per byte using an 8-bit parallel XOR reduction.
//
// Memory map:
//   0x000: DATA    (write) — feed one byte (bits [7:0]), CRC updates immediately
//   0x004: CRC     (read)  — current CRC-32 value (inverted, ready to use)
//   0x008: CONTROL (write) — bit 0 = reset CRC to 0xFFFFFFFF
//   0x00C: RAW     (read)  — raw (non-inverted) CRC state
//   0x010: COUNT   (read)  — number of bytes fed since last reset

module anvil (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] crc;
    logic [31:0] byte_count;

    // CRC-32 one-byte step (reflected polynomial 0xEDB88320)
    function automatic [31:0] crc_byte(input [31:0] crc_in, input [7:0] data);
        logic [31:0] c;
        integer i;
        c = crc_in ^ {24'd0, data};
        for (i = 0; i < 8; i = i + 1) begin
            if (c[0])
                c = (c >> 1) ^ 32'hEDB88320;
            else
                c = c >> 1;
        end
        crc_byte = c;
    endfunction

    // Precompute next CRC combinationally
    wire [31:0] next_crc = crc_byte(crc, reg_wdata[7:0]);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            crc <= 32'hFFFFFFFF;
            byte_count <= 32'd0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: begin // DATA: feed byte
                        crc <= next_crc;
                        byte_count <= byte_count + 32'd1;
                    end
                    3'h2: begin // CONTROL: reset
                        if (reg_wdata[0]) begin
                            crc <= 32'hFFFFFFFF;
                            byte_count <= 32'd0;
                        end
                    end
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= 32'd0;
                    3'h1: reg_rdata <= crc ^ 32'hFFFFFFFF;  // CRC (final XOR)
                    3'h2: reg_rdata <= 32'd0;
                    3'h3: reg_rdata <= crc;                  // RAW
                    3'h4: reg_rdata <= byte_count;           // COUNT
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
