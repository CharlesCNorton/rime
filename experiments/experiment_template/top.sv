// experiment_template: skeleton for new RIME experiments.
// Copy this directory and modify top.sv for a new experiment.
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

    wire       rx_valid;
    wire [7:0] rx_data;
    wire       tx_send;
    wire [7:0] tx_data;

    uart_rx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) RX (
        .clk(sys_clk), .rx(usb_rx), .finish(rx_valid), .data(rx_data)
    );
    uart_tx #(.CLK(CLK_HZ), .BAUD_RATE(BAUD)) TX (
        .clk(sys_clk), .send(tx_send), .data(tx_data), .tx(usb_tx)
    );

    logic [23:0] heartbeat;
    always_ff @(posedge sys_clk) begin
        if (rst) heartbeat <= 24'd0;
        else heartbeat <= heartbeat + 24'd1;
    end


    assign tx_send = rx_valid;
    assign tx_data = rx_data;
    assign led = {heartbeat[23], rx_data[3:0]};

endmodule
