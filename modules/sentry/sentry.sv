// SENTRY: Memory protection unit
// 4 configurable address ranges with R/W permissions.
// CPU writes a test address+mode, SENTRY checks against all regions.
//
// Memory map:
//   0x000: CHECK_ADDR (write) — address to check
//   0x004: CHECK_MODE (write) — bit 0=read, bit 1=write. Triggers check.
//   0x008: RESULT     (read)  — bit 0=allowed, bit 1=trapped
//   0x00C: TRAP_ADDR  (read)  — address of last trap
//   0x010: CONTROL    (write) — bit 0=enable, bit 1=clear trap
//   0x020+i*8: REGION_BASE[i]  (write) — region i start address (i=0..3)
//   0x024+i*8: REGION_CFG[i]   (write) — bits[15:0]=size, bit16=R, bit17=W, bit18=enable

module sentry (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    logic [31:0] region_base [0:3];
    logic [15:0] region_size [0:3];
    logic        region_r    [0:3];
    logic        region_w    [0:3];
    logic        region_en   [0:3];

    logic [31:0] check_addr;
    logic        last_allowed;
    logic        trapped;
    logic [31:0] trap_addr;
    logic        enabled;

    // Combinational check
    wire [31:0] ca = reg_wdata;
    wire        is_read = reg_wdata[0];  // used when CHECK_MODE is being written
    wire        is_write_mode = reg_wdata[1];

    // Check if address falls in any enabled region with matching permission
    integer _i;

    // Check per region
    wire in0 = region_en[0] && check_addr >= region_base[0] && check_addr < (region_base[0] + {16'd0, region_size[0]});
    wire in1 = region_en[1] && check_addr >= region_base[1] && check_addr < (region_base[1] + {16'd0, region_size[1]});
    wire in2 = region_en[2] && check_addr >= region_base[2] && check_addr < (region_base[2] + {16'd0, region_size[2]});
    wire in3 = region_en[3] && check_addr >= region_base[3] && check_addr < (region_base[3] + {16'd0, region_size[3]});

    wire ok0 = in0 && ((is_read && region_r[0]) || (is_write_mode && region_w[0]));
    wire ok1 = in1 && ((is_read && region_r[1]) || (is_write_mode && region_w[1]));
    wire ok2 = in2 && ((is_read && region_r[2]) || (is_write_mode && region_w[2]));
    wire ok3 = in3 && ((is_read && region_r[3]) || (is_write_mode && region_w[3]));

    wire allowed_comb = (!enabled) ? 1'b1 : (ok0 | ok1 | ok2 | ok3);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            enabled <= 1'b0; trapped <= 1'b0;
            trap_addr <= 32'd0; last_allowed <= 1'b0;
            check_addr <= 32'd0;
            for (_i = 0; _i < 4; _i = _i + 1) begin
                region_base[_i] <= 32'd0; region_size[_i] <= 16'd0;
                region_r[_i] <= 1'b0; region_w[_i] <= 1'b0; region_en[_i] <= 1'b0;
            end
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h0: check_addr <= reg_wdata;
                    4'h1: begin // CHECK_MODE: triggers check
                        last_allowed <= allowed_comb;
                        if (!allowed_comb && enabled) begin
                            trapped <= 1'b1;
                            trap_addr <= check_addr;
                        end
                    end
                    4'h4: begin // CONTROL
                        enabled <= reg_wdata[0];
                        if (reg_wdata[1]) trapped <= 1'b0;
                    end
                    // Regions at 0x020, 0x028, 0x030, 0x038
                    4'h8: region_base[0] <= reg_wdata;
                    4'h9: begin region_size[0]<=reg_wdata[15:0]; region_r[0]<=reg_wdata[16]; region_w[0]<=reg_wdata[17]; region_en[0]<=reg_wdata[18]; end
                    4'hA: region_base[1] <= reg_wdata;
                    4'hB: begin region_size[1]<=reg_wdata[15:0]; region_r[1]<=reg_wdata[16]; region_w[1]<=reg_wdata[17]; region_en[1]<=reg_wdata[18]; end
                    4'hC: region_base[2] <= reg_wdata;
                    4'hD: begin region_size[2]<=reg_wdata[15:0]; region_r[2]<=reg_wdata[16]; region_w[2]<=reg_wdata[17]; region_en[2]<=reg_wdata[18]; end
                    4'hE: region_base[3] <= reg_wdata;
                    4'hF: begin region_size[3]<=reg_wdata[15:0]; region_r[3]<=reg_wdata[16]; region_w[3]<=reg_wdata[17]; region_en[3]<=reg_wdata[18]; end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[5:2])
                    4'h2: reg_rdata <= {30'd0, trapped, last_allowed};
                    4'h3: reg_rdata <= trap_addr;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
