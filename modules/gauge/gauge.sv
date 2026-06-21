// GAUGE: General Aggregated Utilization and Granular Estimator
// Bus bandwidth counter. Counts completed bus transactions
// (snoop_valid && snoop_ready) per configurable gate interval.
// A transaction is a "write" if any bit of snoop_wstrb is set,
// otherwise a "read".
//
// Memory map:
//   0x000: GATE     (write) — gate interval in sys_clk cycles
//   0x004: TOTAL    (read)  — total transactions in last completed gate
//   0x008: READS    (read)  — read transactions in last completed gate
//   0x00C: WRITES   (read)  — write transactions in last completed gate
//   0x010: CYCLES   (read)  — gate duration in cycles (= GATE value)
//   0x014: RUNNING  (read)  — current in-progress total transaction count
//   0x018: CONTROL  (write) — bit 0 = start gate, bit 1 = reset

module gauge (
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

    logic [31:0] gate_window;
    logic [31:0] gate_counter;
    logic [31:0] txn_count;
    logic [31:0] read_count;
    logic [31:0] write_count;
    logic [31:0] running_count;
    logic [31:0] result_total;
    logic [31:0] result_reads;
    logic [31:0] result_writes;
    logic        gate_active;

    wire txn_fire     = snoop_valid && snoop_ready;
    wire txn_is_write = (snoop_wstrb != 4'b0000);

    always_ff @(posedge clk) begin
        reg_ready <= 1'b0;

        if (rst) begin
            gate_window   <= 32'd0;
            gate_counter  <= 32'd0;
            txn_count     <= 32'd0;
            read_count    <= 32'd0;
            write_count   <= 32'd0;
            running_count <= 32'd0;
            result_total  <= 32'd0;
            result_reads  <= 32'd0;
            result_writes <= 32'd0;
            gate_active   <= 1'b0;
        end else begin
            if (txn_fire) begin
                running_count <= running_count + 32'd1;
                if (gate_active) begin
                    txn_count <= txn_count + 32'd1;
                    if (txn_is_write)
                        write_count <= write_count + 32'd1;
                    else
                        read_count <= read_count + 32'd1;
                end
            end

            if (gate_active) begin
                if (gate_counter >= gate_window) begin
                    result_total  <= txn_count;
                    result_reads  <= read_count;
                    result_writes <= write_count;
                    gate_active   <= 1'b0;
                end
                gate_counter <= gate_counter + 32'd1;
            end

            if (reg_wr) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: gate_window <= reg_wdata;
                    3'h6: begin
                        if (reg_wdata[1]) begin
                            txn_count     <= 32'd0;
                            read_count    <= 32'd0;
                            write_count   <= 32'd0;
                            running_count <= 32'd0;
                            result_total  <= 32'd0;
                            result_reads  <= 32'd0;
                            result_writes <= 32'd0;
                            gate_active   <= 1'b0;
                        end
                        if (reg_wdata[0]) begin
                            gate_counter <= 32'd0;
                            txn_count    <= 32'd0;
                            read_count   <= 32'd0;
                            write_count  <= 32'd0;
                            gate_active  <= 1'b1;
                        end
                    end
                    default: ;
                endcase
            end

            if (reg_rd) begin
                reg_ready <= 1'b1;
                case (reg_addr[4:2])
                    3'h0: reg_rdata <= gate_window;
                    3'h1: reg_rdata <= result_total;
                    3'h2: reg_rdata <= result_reads;
                    3'h3: reg_rdata <= result_writes;
                    3'h4: reg_rdata <= gate_window;
                    3'h5: reg_rdata <= running_count;
                    default: reg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule
