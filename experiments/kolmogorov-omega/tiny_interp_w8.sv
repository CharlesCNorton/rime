module tiny_interp_w8 (
    input wire clk,input wire rst,input wire start,
    input wire [23:0] program,input wire [7:0] init_a,input wire [7:0] init_b,
    input wire [23:0] isa_lut,
    output logic [7:0] result,output logic done,output logic halted);
    localparam integer MAX_STEPS=256,PROG_LEN=8;
    logic [7:0] a,b;logic [3:0] pc;logic [8:0] step;logic running;
    logic [2:0] raw_op;
    always_comb case(pc)
        4'd0:raw_op=program[2:0];
        4'd1:raw_op=program[5:3];
        4'd2:raw_op=program[8:6];
        4'd3:raw_op=program[11:9];
        4'd4:raw_op=program[14:12];
        4'd5:raw_op=program[17:15];
        4'd6:raw_op=program[20:18];
        4'd7:raw_op=program[23:21];
        default:raw_op=3'd5;endcase
    logic [3:0] op_id;
    always_comb case(raw_op)
        3'd0:op_id=isa_lut[3:0];
        3'd1:op_id=isa_lut[7:4];
        3'd2:op_id=isa_lut[11:8];
        3'd3:op_id=isa_lut[15:12];
        3'd4:op_id=isa_lut[19:16];
        3'd5:op_id=isa_lut[23:20];
        default:op_id=4'd14;endcase
    always_ff @(posedge clk) begin done<=0;
        if(rst) begin running<=0;a<=0;b<=0;pc<=0;step<=0;result<=0;halted<=0;end
        else if(start) begin running<=1;a<=init_a;b<=init_b;pc<=0;step<=0;halted<=0;end
        else if(running) begin
            if(pc>=PROG_LEN) begin result<=a;halted<=1;done<=1;running<=0;end
            else if(step>=MAX_STEPS) begin result<=a;halted<=0;done<=1;running<=0;end
            else begin step<=step+1;case(op_id)
                0:begin a<=a+1;pc<=pc+1;end
                1:begin a<=a-1;pc<=pc+1;end
                2:begin a<=b;b<=a;pc<=pc+1;end
                3:begin a<=a+b;pc<=pc+1;end
                4:begin a<=a^b;pc<=pc+1;end
                5:begin if(a!=0)pc<=0;else pc<=pc+1;end
                6:begin a<=-a;pc<=pc+1;end
                7:begin b<=a;pc<=pc+1;end
                8:begin a<=a-b;pc<=pc+1;end
                9:begin a<=a&b;pc<=pc+1;end
                10:begin a<=a|b;pc<=pc+1;end
                11:begin a<=a>>1;pc<=pc+1;end
                12:begin a<={a[6:0],1'b0};pc<=pc+1;end
                13:begin a<=~a;pc<=pc+1;end
                14:begin pc<=pc+1;end
                15:begin result<=a;halted<=1;done<=1;running<=0;end
            endcase end end end endmodule
