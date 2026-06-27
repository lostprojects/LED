// Art-Net DMX Packet Parser & Plug-and-Play Universe Auto-Detection
// Automatically detects panel sizes and timing based on incoming universes.

`default_nettype none
`include "config.vh"

module udp_panel_writer (
    input  wire          clock,
    input  wire          reset,
    input  wire          button,
    input  wire          udp_source_valid,
    input  wire          udp_source_last,
    output reg           udp_source_ready,
    input  wire  [15:0]  udp_source_src_port,
    input  wire  [15:0]  udp_source_dst_port,
    input  wire  [31:0]  udp_source_ip_address,
    input  wire  [15:0]  udp_source_length,
    input  wire  [31:0]  udp_source_data,
    input  wire  [3:0]   udp_source_error,

    output reg [`NUM_ACTIVE_PORTS-1:0] ctrl_en,
    output wire [3:0]    ctrl_wr,
    output reg [15:0]    ctrl_addr,
    output reg [23:0]    ctrl_wdat,

    output reg           led_reg,
    output reg           packet_recv_toggle,

    // Runtime Configuration Outputs (Flat vectors for verilog compatibility)
    output reg [4*`NUM_ACTIVE_PORTS-1:0] cfg_phys_port_flat,
    output reg [2*`NUM_ACTIVE_PORTS-1:0] cfg_panel_type_flat,
    output reg [6*`NUM_ACTIVE_PORTS-1:0] cfg_max_active_y_flat,
    output reg [8*`NUM_ACTIVE_PORTS-1:0] cfg_start_active_x_flat,
    output reg [31:0]                    cfg_board_ip,
    output wire                          button_hold_active,
    output wire                          button_hold_done,
    output wire                          button_hold_blink
);

    assign ctrl_wr = 4'b0111; // always write R, G, B

    localparam STATE_WAIT_PACKET = 2'd0,
               STATE_HEADER      = 2'd1,
               STATE_DMX_DATA    = 2'd2;

    reg [1:0]  state;
    reg [15:0] byte_cnt;
    
    reg [14:0] universe;
    reg [15:0] length;
    reg [15:0] dmx_channel_cnt;

    reg [7:0]  pixel_r;
    reg [7:0]  pixel_g;
    reg [7:0]  universe_lsb;

    // Diagnostic LED (toggle on packet receipt)
    reg [23:0] led_counter;
    always @(posedge clock) begin
        if (reset) begin
            led_reg <= 1'b1;
            led_counter <= 0;
        end else if (state == STATE_DMX_DATA && udp_source_valid) begin
            led_counter <= led_counter + 1;
            led_reg <= led_counter[20];
        end
    end

    // Toggle signal for CDC watchdog
    always @(posedge clock) begin
        if (reset) begin
            packet_recv_toggle <= 1'b0;
        end else begin
            if (state == STATE_WAIT_PACKET && udp_source_valid && (udp_source_dst_port == 16'h1936)) begin
                if (udp_source_data[7:0] == 8'h41) begin // 'A'
                    packet_recv_toggle <= !packet_recv_toggle;
                end
            end
        end
    end

    // DMX index channels
    reg [1:0]  pixel_sub_cnt;
    reg [8:0]  pixel_idx;

    // Art-Net mapping (pipelined)
    reg [7:0]  panel_id_reg;
    reg [7:0]  local_universe_reg;
    reg [15:0] universe_pixel_offset;

    wire [15:0] global_pixel = universe_pixel_offset + pixel_idx;

    // Button synchronizer and hold counter
    reg        button_sync0 = 1'b1;
    reg        button_sync1 = 1'b1;
    reg [30:0] button_hold_cnt = 0;

    always @(posedge clock) begin
        if (reset) begin
            button_sync0    <= 1'b1;
            button_sync1    <= 1'b1;
            button_hold_cnt <= 0;
        end else begin
            button_sync0 <= button;
            button_sync1 <= button_sync0;
            
            if (button_sync1 == 1'b0) begin // Button pressed (active-low)
                if (button_hold_cnt < 31'd1250000000) begin
                    button_hold_cnt <= button_hold_cnt + 1'b1;
                end
            end else begin
                button_hold_cnt <= 0;
            end
        end
    end

    always @(posedge clock) begin
        if (reset) begin
            udp_source_ready <= 1'b0;
            state            <= STATE_WAIT_PACKET;
            byte_cnt         <= 0;
            universe         <= 0;
            length           <= 0;
            dmx_channel_cnt  <= 0;
            pixel_r          <= 0;
            pixel_g          <= 0;
            pixel_sub_cnt    <= 0;
            pixel_idx        <= 0;
            ctrl_en          <= 0;
            ctrl_addr        <= 0;
            ctrl_wdat        <= 0;
            universe_lsb     <= 0;
            cfg_board_ip     <= 32'd168430090; // Default 10.10.10.10
        end else begin
            ctrl_en <= {`NUM_ACTIVE_PORTS{1'b0}};
            
            // IP override by button hold (10 seconds)
            if (button_hold_cnt == 31'd1250000000) begin
                cfg_board_ip <= 32'd168430090; // Revert to 10.10.10.10
            end
            
            case (state)
                STATE_WAIT_PACKET: begin
                    udp_source_ready <= 1'b1;
                    byte_cnt         <= 0;
                    if (udp_source_valid && (udp_source_dst_port == 16'h1936)) begin
                        if (udp_source_data[7:0] == 8'h41) begin
                            byte_cnt <= 1;
                            state    <= STATE_HEADER;
                        end
                    end
                end

                STATE_HEADER: begin
                    if (udp_source_valid) begin
                        byte_cnt <= byte_cnt + 1;
                        
                        case (byte_cnt)
                            1:  if (udp_source_data[7:0] != 8'h72) state <= STATE_WAIT_PACKET; // 'r'
                            2:  if (udp_source_data[7:0] != 8'h74) state <= STATE_WAIT_PACKET; // 't'
                            3:  if (udp_source_data[7:0] != 8'h2d) state <= STATE_WAIT_PACKET; // '-'
                            4:  if (udp_source_data[7:0] != 8'h4e) state <= STATE_WAIT_PACKET; // 'N'
                            5:  if (udp_source_data[7:0] != 8'h65) state <= STATE_WAIT_PACKET; // 'e'
                            6:  if (udp_source_data[7:0] != 8'h74) state <= STATE_WAIT_PACKET; // 't'
                            7:  if (udp_source_data[7:0] != 8'h00) state <= STATE_WAIT_PACKET; // '\0'
                            8:  if (udp_source_data[7:0] != 8'h00) state <= STATE_WAIT_PACKET; // OpCode LSB
                            9:  if (udp_source_data[7:0] != 8'h50) state <= STATE_WAIT_PACKET; // OpCode MSB
                            14: universe_lsb <= udp_source_data[7:0];
                            15: begin
                                universe <= {udp_source_data[6:0], universe_lsb};
                            end
                            16: length[15:8] <= udp_source_data[7:0];
                            17: begin
                                length[7:0]     <= udp_source_data[7:0];
                                dmx_channel_cnt <= 0;
                                pixel_sub_cnt   <= 0;
                                pixel_idx       <= 0;
                                state           <= STATE_DMX_DATA;
                            end
                        endcase

                        if (udp_source_last && byte_cnt < 17) begin
                            state <= STATE_WAIT_PACKET;
                        end
                    end
                end

                STATE_DMX_DATA: begin
                    if (udp_source_valid) begin
                        dmx_channel_cnt <= dmx_channel_cnt + 1;
                        
                        // Config and IP override via Universe 666
                        if (universe == 15'd666) begin
                            case (dmx_channel_cnt)
                                16'd0: cfg_board_ip[31:24] <= udp_source_data[7:0];
                                16'd1: cfg_board_ip[23:16] <= udp_source_data[7:0];
                                16'd2: cfg_board_ip[15:8]  <= udp_source_data[7:0];
                                16'd3: cfg_board_ip[7:0]   <= udp_source_data[7:0];
                                
                                // J1
                                16'd4: cfg_panel_type[0]     <= udp_source_data[1:0];
                                16'd5: cfg_max_active_y[0]   <= udp_source_data[5:0];
                                16'd6: cfg_start_active_x[0] <= udp_source_data[7:0];
                                
                                // J2
                                16'd7: cfg_panel_type[1]     <= udp_source_data[1:0];
                                16'd8: cfg_max_active_y[1]   <= udp_source_data[5:0];
                                16'd9: cfg_start_active_x[1] <= udp_source_data[7:0];
                                
                                // J3
                                16'd10: cfg_panel_type[2]     <= udp_source_data[1:0];
                                16'd11: cfg_max_active_y[2]   <= udp_source_data[5:0];
                                16'd12: cfg_start_active_x[2] <= udp_source_data[7:0];
                                
                                // J4
                                16'd13: cfg_panel_type[3]     <= udp_source_data[1:0];
                                16'd14: cfg_max_active_y[3]   <= udp_source_data[5:0];
                                16'd15: cfg_start_active_x[3] <= udp_source_data[7:0];
                                
                                // J5
                                16'd16: cfg_panel_type[4]     <= udp_source_data[1:0];
                                16'd17: cfg_max_active_y[4]   <= udp_source_data[5:0];
                                16'd18: cfg_start_active_x[4] <= udp_source_data[7:0];
                                
                                // J6
                                16'd19: cfg_panel_type[5]     <= udp_source_data[1:0];
                                16'd20: cfg_max_active_y[5]   <= udp_source_data[5:0];
                                16'd21: cfg_start_active_x[5] <= udp_source_data[7:0];
                                
                                // J7
                                16'd22: cfg_panel_type[6]     <= udp_source_data[1:0];
                                16'd23: cfg_max_active_y[6]   <= udp_source_data[5:0];
                                16'd24: cfg_start_active_x[6] <= udp_source_data[7:0];
                                
                                // J8
                                16'd25: cfg_panel_type[7]     <= udp_source_data[1:0];
                                16'd26: cfg_max_active_y[7]   <= udp_source_data[5:0];
                                16'd27: cfg_start_active_x[7] <= udp_source_data[7:0];
                                
                                // J9
                                16'd28: cfg_panel_type[8]     <= udp_source_data[1:0];
                                16'd29: cfg_max_active_y[8]   <= udp_source_data[5:0];
                                16'd30: cfg_start_active_x[8] <= udp_source_data[7:0];
                                
                                // J10
                                16'd31: cfg_panel_type[9]     <= udp_source_data[1:0];
                                16'd32: cfg_max_active_y[9]   <= udp_source_data[5:0];
                                16'd33: cfg_start_active_x[9] <= udp_source_data[7:0];
                                
                                // J11
                                16'd34: cfg_panel_type[10]    <= udp_source_data[1:0];
                                16'd35: cfg_max_active_y[10]  <= udp_source_data[5:0];
                                16'd36: cfg_start_active_x[10]<= udp_source_data[7:0];
                                
                                // J12
                                16'd37: cfg_panel_type[11]    <= udp_source_data[1:0];
                                16'd38: cfg_max_active_y[11]  <= udp_source_data[5:0];
                                16'd39: cfg_start_active_x[11]<= udp_source_data[7:0];
                            endcase
                        end
                        
                        if (pixel_sub_cnt == 0) begin
                            pixel_r       <= udp_source_data[7:0];
                            pixel_sub_cnt <= 1;
                        end else if (pixel_sub_cnt == 1) begin
                            pixel_g       <= udp_source_data[7:0];
                            pixel_sub_cnt <= 2;
                        end else begin
                            pixel_sub_cnt <= 0;
                            pixel_idx     <= pixel_idx + 1;
                            
                            if (panel_id_reg < `NUM_ACTIVE_PORTS && global_pixel < 4096) begin
                                ctrl_en   <= (`NUM_ACTIVE_PORTS'b1 << panel_id_reg);
                                ctrl_addr <= target_write_addr;
                                ctrl_wdat <= {2'b0, pixel_r[7:2], 2'b0, pixel_g[7:2], 2'b0, udp_source_data[7:2]};
                            end
                        end

                        if (udp_source_last || (dmx_channel_cnt >= length - 1)) begin
                            state <= STATE_WAIT_PACKET;
                        end
                    end
                end
            endcase
        end
    end

    // =========================================================================
    // Plug-and-Play Universe Auto-Detection
    // =========================================================================

    reg [3:0] cfg_phys_port [0:`NUM_ACTIVE_PORTS-1];
    reg [1:0] cfg_panel_type [0:`NUM_ACTIVE_PORTS-1];
    reg [5:0] cfg_max_active_y [0:`NUM_ACTIVE_PORTS-1];
    reg [7:0] cfg_start_active_x [0:`NUM_ACTIVE_PORTS-1];

    wire [7:0]  next_panel_id = universe >> 5;           // universe / 32
    wire [5:0]  next_local_u  = {1'b0, universe[4:0]};   // universe % 32
    wire [15:0] next_offset   = {10'b0, next_local_u} << 7;

    wire [15:0] target_write_addr = (cfg_panel_type[panel_id_reg] == 2'd3) ? (
                                        {4'b0, global_pixel[10], global_pixel[9:5], global_pixel[11], global_pixel[4:0]}
                                    ) : (
                                        (cfg_panel_type[panel_id_reg] == 2'd2 && cfg_start_active_x[panel_id_reg] == 8'd96) ? (
                                            {5'b0, global_pixel[9:5], 1'b0, global_pixel[4:0]}
                                        ) : global_pixel
                                    );

    always @(posedge clock) begin
        if (reset) begin
            panel_id_reg          <= 0;
            local_universe_reg    <= 0;
            universe_pixel_offset <= 0;
        end else begin
            panel_id_reg          <= next_panel_id;
            local_universe_reg    <= {2'b0, next_local_u};
            universe_pixel_offset <= next_offset;
        end
    end

    integer p_idx;
    always @(posedge clock) begin
        if (reset) begin
            // Default configs:
            // - Logical port maps to physical J-port directly
            // - Standard 64x64 on J1-J7, stacked 32x64 on J8-J12
            for (p_idx = 0; p_idx < `NUM_ACTIVE_PORTS; p_idx = p_idx + 1) begin
                cfg_phys_port[p_idx]      <= p_idx[3:0];
                cfg_panel_type[p_idx]     <= (p_idx >= 7) ? 2'd1 : 2'd0; // stacked (1) on J8-J12, standard (0) on J1-J7
                cfg_max_active_y[p_idx]   <= (p_idx >= 7) ? 6'd16 : 6'd32;
                cfg_start_active_x[p_idx] <= (p_idx >= 7) ? 8'd0 : 8'd64; // Correct start active x default for stacked (0) vs standard (64)
            end
        end
    end

    // Flat register vectors to top level mapping
    integer f_idx;
    always @(*) begin
        for (f_idx = 0; f_idx < `NUM_ACTIVE_PORTS; f_idx = f_idx + 1) begin
            cfg_phys_port_flat[4*f_idx +: 4]      = cfg_phys_port[f_idx];
            cfg_panel_type_flat[2*f_idx +: 2]     = cfg_panel_type[f_idx];
            cfg_max_active_y_flat[6*f_idx +: 6]   = cfg_max_active_y[f_idx];
            cfg_start_active_x_flat[8*f_idx +: 8] = cfg_start_active_x[f_idx];
        end
    end

    assign button_hold_active = (button_hold_cnt > 0);
    assign button_hold_done   = (button_hold_cnt >= 31'd1250000000);
    assign button_hold_blink  = button_hold_cnt[23];

endmodule
