// FERRY: Fast External Register Relay Engine
// Self-contained DMA: 16-word internal scratchpad. CPU writes source data,
// programs src/dst/count, triggers transfer. The engine copies words from
// SRC region to DST region inside its own scratchpad.
//
// This is a simplified DMA that operates on internal storage rather than
// the CPU bus, so it can be tested and verified without needing bus mastering.
//
// Memory map:
//   0x000-0x03C: SCRATCH[0..15] (write/read) — 16-word scratchpad
//   0x040: SRC      (write) — source index (0..15)
//   0x044: DST      (write) — destination index (0..15)
//   0x048: COUNT    (write) — number of words to copy
//   0x04C: CONTROL  (write) — bit 0 = start, bit 1 = reset
//   0x050: STATUS   (read)  — bit 0 = busy, bit 1 = done
//   0x054: TRANSFERS (read) — total transfers completed since reset

module ferry (
    input  wire        clk,
    input  wire        rst,

    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] scratch [0:15];
    logic [3:0]  src, dst;
    logic [4:0]  count;
    logic [3:0]  cur_src, cur_dst;
    logic [4:0]  remaining;
    logic        busy, done;
    logic [31:0] transfers;

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            for (integer i = 0; i < 16; i = i + 1) scratch[i] <= 32'd0;
            src <= 4'd0; dst <= 4'd0; count <= 5'd0;
            cur_src <= 4'd0; cur_dst <= 4'd0; remaining <= 5'd0;
            busy <= 1'b0; done <= 1'b0;
            transfers <= 32'd0;
        end else begin
            if (busy) begin
                if (remaining != 5'd0) begin
                    scratch[cur_dst] <= scratch[cur_src];
                    cur_src <= cur_src + 4'd1;
                    cur_dst <= cur_dst + 4'd1;
                    remaining <= remaining - 5'd1;
                end else begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    transfers <= transfers + 32'd1;
                end
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0) begin
                    // SCRATCH[i] at offset i*4
                    scratch[reg_addr[5:2]] <= reg_wdata;
                end else case (reg_addr[5:2])
                    4'h0: src   <= reg_wdata[3:0];
                    4'h1: dst   <= reg_wdata[3:0];
                    4'h2: count <= reg_wdata[4:0];
                    4'h3: begin
                        if (reg_wdata[1]) begin
                            busy <= 1'b0; done <= 1'b0;
                            transfers <= 32'd0;
                        end
                        if (reg_wdata[0]) begin
                            cur_src <= src;
                            cur_dst <= dst;
                            remaining <= count;
                            busy <= 1'b1;
                            done <= 1'b0;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                if (reg_addr[6] == 1'b0) begin
                    reg_rdata <= scratch[reg_addr[5:2]];
                end else case (reg_addr[5:2])
                    4'h4: reg_rdata <= {30'd0, done, busy};
                    4'h5: reg_rdata <= transfers;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
