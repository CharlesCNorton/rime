// RIME-I standalone test wrapper: clock divider, BRAM with firmware
// loaded via $readmemh, UART TX/RX, and rime_i_core. Used by test_isa.py
// and test_slabs.py for ISA and memory verification on silicon.

module top (
    input  wire       clk,
    input  wire       usb_rx,
    output wire       usb_tx,
    output logic [4:0] led,
    input  wire [1:0] button
);
    localparam integer CLK_HZ = 25000000;
    localparam integer BAUD   = 115200;

    logic sys_clk;
    always_ff @(posedge clk) begin
        if (~button[0]) sys_clk <= 1'b0;
        else sys_clk <= ~sys_clk;
    end

    logic [3:0] startup_cnt;
    logic       startup_done;
    always_ff @(posedge sys_clk) begin
        if (~button[0]) begin
            startup_cnt  <= 4'd0;
            startup_done <= 1'b0;
        end else if (!startup_done) begin
            if (startup_cnt == 4'd15) startup_done <= 1'b1;
            else startup_cnt <= startup_cnt + 4'd1;
        end
    end
    wire rst = ~button[0] || !startup_done;

    rime_i_top #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) SOC (
        .clk(sys_clk), .rst(rst),
        .uart_tx(usb_tx), .uart_rx(usb_rx)
    );

    logic [23:0] heartbeat;
    always_ff @(posedge sys_clk) begin
        if (rst) heartbeat <= 24'd0;
        else heartbeat <= heartbeat + 24'd1;
    end
    assign led = {heartbeat[23], SOC.CPU.state[2:0], startup_done};

endmodule
