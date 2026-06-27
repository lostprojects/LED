// 2048-entry by 9-bit dual-port RAM module (inferred as block RAM)
module panel_ram_2k (
    input  wire        write_clk,
    input  wire        write_en,
    input  wire [10:0] write_addr,
    input  wire [8:0]  write_data,
    
    input  wire        read_clk,
    input  wire [10:0] read_addr,
    output reg  [8:0]  read_data
);
    reg [8:0] mem [2047:0];
    
    always @(posedge write_clk) begin
        if (write_en) begin
            mem[write_addr] <= write_data;
        end
    end
    
    always @(posedge read_clk) begin
        read_data <= mem[read_addr];
    end
endmodule

// Main Driver
module hub75_driver (
    input  wire        clk_25m,
    
    // Write side
    input  wire        write_clk,
    input  wire        write_en,
    input  wire [3:0]  panel_id,
    input  wire [11:0] write_addr,
    input  wire [8:0]  write_val,

    // HUB75E Outputs
    output reg  [15:0] hub75_r1, output reg [15:0] hub75_g1, output reg [15:0] hub75_b1,
    output reg  [15:0] hub75_r2, output reg [15:0] hub75_g2, output reg [15:0] hub75_b2,
    output reg         hub75_a, output reg hub75_b, output reg hub75_c, output reg hub75_d, output reg hub75_e,
    output reg         hub75_clk,
    output reg         hub75_lat,
    output reg         hub75_oe
);
    // Wire connections for the parallel memory blocks
    wire [8:0] read_data_1 [15:0];
    wire [8:0] read_data_2 [15:0];

    // Scanning Coordinates
    reg [4:0]  row;          // 0 to 31
    reg [5:0]  col;          // 0 to 63
    reg [1:0]  state;
    reg [2:0]  pwm_counter;  // 3-bit depth (0-7 steps)

    wire [10:0] addr_read = {row, col};

    // Instantiate 32 separate RAM blocks (100% fits in ECP5-25F)
    genvar p;
    generate
        for (p = 0; p < 16; p = p + 1) begin : gen_rams
            // UPPER Half Framebuffer (Rows 0-31)
            panel_ram_2k ram_upper (
                .write_clk(write_clk),
                .write_en(write_en && (panel_id == p) && !write_addr[11]),
                .write_addr(write_addr[10:0]),
                .write_data(write_val),
                .read_clk(clk_25m),
                .read_addr(addr_read),
                .read_data(read_data_1[p])
            );

            // LOWER Half Framebuffer (Rows 32-63)
            panel_ram_2k ram_lower (
                .write_clk(write_clk),
                .write_en(write_en && (panel_id == p) && write_addr[11]),
                .write_addr(write_addr[10:0]),
                .write_data(write_val),
                .read_clk(clk_25m),
                .read_addr(addr_read),
                .read_data(read_data_2[p])
            );

            // Assign parallel digital lines to ports
            always @(posedge clk_25m) begin
                if (state == 0) begin
                    hub75_r1[p] <= (read_data_1[p][8:6] > pwm_counter);
                    hub75_g1[p] <= (read_data_1[p][5:3] > pwm_counter);
                    hub75_b1[p] <= (read_data_1[p][2:0] > pwm_counter);

                    hub75_r2[p] <= (read_data_2[p][8:6] > pwm_counter);
                    hub75_g2[p] <= (read_data_2[p][5:3] > pwm_counter);
                    hub75_b2[p] <= (read_data_2[p][2:0] > pwm_counter);
                end
            end
        end
    endgenerate

    // State Machine
    always @(posedge clk_25m) begin
        {hub75_e, hub75_d, hub75_c, hub75_b, hub75_a} <= row;
        hub75_lat <= 1'b0;

        case (state)
            0: begin
                hub75_oe  <= 1'b1;
                hub75_clk <= ~hub75_clk;
                
                if (hub75_clk) begin
                    if (col == 63) begin
                        col       <= 0;
                        state     <= 1;
                        hub75_clk <= 1'b0;
                    end else begin
                        col <= col + 1;
                    end
                end
            end
            1: begin
                hub75_lat <= 1'b1;
                state     <= 2;
            end
            2: begin
                hub75_oe <= 1'b0;
                pwm_counter <= pwm_counter + 1;
                if (pwm_counter == 7) begin
                    row   <= row + 1;
                    state <= 0;
                end
            end
        endcase
    end
endmodule
