// QUILL: 4-channel byte buffer
// Each channel is an 8-byte circular FIFO with independent read/write pointers.
//
// Memory map:
//   0x000: TX_DATA (write) — push byte to selected channel
//   0x004: CHANNEL (write) — select channel (0-3)
//   0x008: STATUS  (read)  — bits [3:0] = per-channel has-data
//   0x00C: RX_DATA (read)  — pop oldest byte from selected channel
//   0x010: COUNT   (read)  — byte count of selected channel
//   0x014: CONTROL (write) — bit 0 = clear all

module quill (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        reg_wr,
    input  wire        reg_rd,
    output logic [31:0] reg_rdata,
    output logic        reg_ready
);

    // Channel 0
    logic [7:0] f0 [0:7];
    logic [2:0] wp0, rp0;
    logic [3:0] c0;

    // Channel 1
    logic [7:0] f1 [0:7];
    logic [2:0] wp1, rp1;
    logic [3:0] c1;

    // Channel 2
    logic [7:0] f2 [0:7];
    logic [2:0] wp2, rp2;
    logic [3:0] c2;

    // Channel 3
    logic [7:0] f3 [0:7];
    logic [2:0] wp3, rp3;
    logic [3:0] c3;

    logic [1:0] sel;

    wire [3:0] cur_cnt = (sel==0) ? c0 : (sel==1) ? c1 : (sel==2) ? c2 : c3;
    wire [7:0] cur_head = (sel==0) ? f0[rp0] : (sel==1) ? f1[rp1] : (sel==2) ? f2[rp2] : f3[rp3];

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;
        if (rst) begin
            wp0<=0; rp0<=0; c0<=0;
            wp1<=0; rp1<=0; c1<=0;
            wp2<=0; rp2<=0; c2<=0;
            wp3<=0; rp3<=0; c3<=0;
            sel<=0;
        end else begin
            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: case (sel) // TX push
                        2'd0: if(c0<8) begin f0[wp0]<=reg_wdata[7:0]; wp0<=wp0+1; c0<=c0+1; end
                        2'd1: if(c1<8) begin f1[wp1]<=reg_wdata[7:0]; wp1<=wp1+1; c1<=c1+1; end
                        2'd2: if(c2<8) begin f2[wp2]<=reg_wdata[7:0]; wp2<=wp2+1; c2<=c2+1; end
                        2'd3: if(c3<8) begin f3[wp3]<=reg_wdata[7:0]; wp3<=wp3+1; c3<=c3+1; end
                    endcase
                    3'h1: sel <= reg_wdata[1:0];
                    3'h5: begin
                        if (reg_wdata[0]) begin
                            wp0<=0; rp0<=0; c0<=0;
                            wp1<=0; rp1<=0; c1<=0;
                            wp2<=0; rp2<=0; c2<=0;
                            wp3<=0; rp3<=0; c3<=0;
                        end
                    end
                endcase
            end
            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h2: reg_rdata <= {28'd0, c3!=0, c2!=0, c1!=0, c0!=0};
                    3'h3: begin // RX pop
                        if (cur_cnt > 0) begin
                            reg_rdata <= {24'd0, cur_head};
                            case (sel)
                                2'd0: begin rp0<=rp0+1; c0<=c0-1; end
                                2'd1: begin rp1<=rp1+1; c1<=c1-1; end
                                2'd2: begin rp2<=rp2+1; c2<=c2-1; end
                                2'd3: begin rp3<=rp3+1; c3<=c3-1; end
                            endcase
                        end else
                            reg_rdata <= 32'hFFFFFFFF;
                    end
                    3'h4: reg_rdata <= {28'd0, cur_cnt};
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
