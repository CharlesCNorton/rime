// thermal-geometry: minimal test module for placement constraint validation.
// Small ring-oscillator array used to verify nextpnr placement scripts.
module top (
    input wire clk, input wire usb_rx, output wire usb_tx,
    output logic [4:0] led, input wire [1:0] button,
    output wire flash_csn, output wire flash_mosi,
    output wire flash_wpn, output wire flash_resetn, input wire flash_miso,
    output wire sd_clk, output wire sd_csn, output wire sd_mosi,
    input wire sd_miso, input wire sd_det,
    output wire sdram_clk, output wire sdram_cke, output wire sdram_csn,
    output wire sdram_rasn, output wire sdram_casn, output wire sdram_wen,
    output wire [1:0] sdram_ba, output wire [12:0] sdram_a,
    inout wire [15:0] sdram_dq, output wire [1:0] sdram_dqm
);
    assign flash_csn=1; assign flash_mosi=0; assign flash_wpn=1; assign flash_resetn=1;
    assign sd_clk=0; assign sd_csn=1; assign sd_mosi=1;
    assign sdram_clk=0; assign sdram_cke=0; assign sdram_csn=1;
    assign sdram_rasn=1; assign sdram_casn=1; assign sdram_wen=1;
    assign sdram_ba=0; assign sdram_a=0; assign sdram_dqm=2'b11;
    assign sdram_dq=16'bz;
    assign usb_tx = 1;

    wire [3:0] ring_out;
    genvar ri;
    generate for (ri=0; ri<4; ri=ri+1) begin : gen_ring
        (* keep *) wire [5:0] r;
        assign r[0] = r[5];
        genvar st;
        for (st=0; st<5; st=st+1) begin : gen_st
            (* keep *) LUT4 #(.INIT(16'h5555)) inv(
                .Z(r[st+1]), .A(r[st]), .B(1'b0), .C(1'b0), .D(1'b0)
            );
        end
        assign ring_out[ri] = r[1];
    end endgenerate

    logic [23:0] hb;
    always_ff @(posedge clk) begin hb <= hb + 1; end
    assign led = {hb[23], ring_out};
endmodule
