// Top-Level Module for Configurable Multi-Size, Multi-Port HUB75 Art-Net Controller
// Drives up to 16 physical HUB75 output ports.

`default_nettype none
`include "config.vh"

module top (
    input wire osc25m,
    
    // RGMII interface
    input  wire                       rgmii_rx_clk,
    input  wire [3:0]                 rgmii_rxd,
    input  wire                       rgmii_rx_ctl,
    output wire                       rgmii_tx_clk,
    output wire [3:0]                 rgmii_txd,
    output wire                       rgmii_tx_ctl,
    
    // MDIO interface
    output wire mdio_scl,
    output wire mdio_sda,
    
    // USER I/O
    input wire button,
    output wire led,
    output wire phy_resetn,

    // HUB75 output ports (expanded to 16)
    output wire [15:0] R0,
    output wire [15:0] G0,
    output wire [15:0] B0,
    output wire [15:0] R1,
    output wire [15:0] G1,
    output wire [15:0] B1,

    // Shared controls
    output wire A,
    output wire B,
    output wire C,
    output wire D,
    output wire E,
    output wire LAT,
    output wire OE,
    output wire CLK
);

    //------------------------------------------------------------------
    // PLL Instantiation and Locked Reset generation
    //------------------------------------------------------------------

    wire phy_init_done;
    wire                 locked;
    wire                 clock;
    reg [3:0]            locked_reset = 4'b1111;
    wire                 reset = locked_reset[3];
    wire                 clk_52m;
    wire                 display_clock = clk_52m;

    pll pll_inst(
        .clkin(osc25m),
        .clk_125m(clock),
        .clk_52m(clk_52m),
        .locked(locked)
    );

    always @(posedge clock or negedge locked) begin
        if (locked == 1'b0) begin
            locked_reset <= 4'b1111;
        end else begin
            locked_reset <= {locked_reset[2:0], 1'b0};
        end
    end

    wire          udp_sink_valid       = 1'b0;
    wire          udp_sink_last        = 1'b0;
    wire          udp_sink_ready       ;
    wire  [15:0]  udp_sink_src_port    = 16'b0;
    wire  [15:0]  udp_sink_dst_port    = 16'b0;
    wire  [31:0]  udp_sink_ip_address  = 32'b0;
    wire  [15:0]  udp_sink_length      = 16'b0;
    wire  [31:0]  udp_sink_data        = 32'b0;
    wire  [3:0]   udp_sink_error       = 4'b0;
    wire          udp_source_valid     ;
    wire          udp_source_last      ;
    wire          udp_source_ready     ;
    wire  [15:0]  udp_source_src_port  ;
    wire  [15:0]  udp_source_dst_port  ;
    wire  [31:0]  udp_source_ip_address;
    wire  [15:0]  udp_source_length    ;
    wire  [31:0]  udp_source_data      ;
    wire  [3:0]   udp_source_error     ;

    wire seq_phy_resetn;
    phy_sequencer phy_sequencer_inst (
        .clock(clock),
        .reset(reset),
        .phy_resetn(seq_phy_resetn),
        .mdio_scl(mdio_scl),
        .mdio_sda(mdio_sda),
        .phy_init_done(phy_init_done)
    );

    assign phy_resetn = 1'b1; // Keep PHY out of reset

    liteeth_core eternit (
        .ip_address           (cfg_board_ip         ),
        .sys_clock            (clock                ),
        .sys_reset            (reset | ~phy_init_done),
        .rgmii_eth_clocks_tx  (rgmii_tx_clk         ),
        .rgmii_eth_clocks_rx  (rgmii_rx_clk         ),
        .rgmii_eth_rst_n      (                     ),
        .rgmii_eth_int_n      (                     ),
        .rgmii_eth_mdio       (                     ),
        .rgmii_eth_mdc        (                     ),
        .rgmii_eth_rx_ctl     (rgmii_rx_ctl         ),
        .rgmii_eth_rx_data    (rgmii_rxd            ),
        .rgmii_eth_tx_ctl     (rgmii_tx_ctl         ),
        .rgmii_eth_tx_data    (rgmii_txd            ),
        .udp_sink_valid       (udp_sink_valid       ),
        .udp_sink_last        (udp_sink_last        ),
        .udp_sink_ready       (udp_sink_ready       ),
        .udp_sink_src_port    (udp_sink_src_port    ),
        .udp_sink_dst_port    (udp_sink_dst_port    ),
        .udp_sink_ip_address  (udp_sink_ip_address  ),
        .udp_sink_length      (udp_sink_length      ),
        .udp_sink_data        (udp_sink_data        ),
        .udp_sink_error       (udp_sink_error       ),
        .udp_source_valid     (udp_source_valid     ),
        .udp_source_last      (udp_source_last      ),
        .udp_source_ready     (udp_source_ready     ),
        .udp_source_src_port  (udp_source_src_port  ),
        .udp_source_dst_port  (udp_source_dst_port  ),
        .udp_source_ip_address(udp_source_ip_address),
        .udp_source_length    (udp_source_length    ),
        .udp_source_data      (udp_source_data      ),
        .udp_source_error     (udp_source_error     )
    );

    wire [`NUM_ACTIVE_PORTS-1:0] ctrl_en;
    wire [3:0]                   ctrl_wr;
    wire [15:0]                  ctrl_addr;
    wire [23:0]                  ctrl_wdat;
    wire                         udp_led;
    wire                         packet_recv_toggle;

    // Config wires flat from parser
    wire [4*`NUM_ACTIVE_PORTS-1:0] cfg_phys_port_flat;
    wire [2*`NUM_ACTIVE_PORTS-1:0] cfg_panel_type_flat;
    wire [6*`NUM_ACTIVE_PORTS-1:0] cfg_max_active_y_flat;
    wire [8*`NUM_ACTIVE_PORTS-1:0] cfg_start_active_x_flat;
    wire [31:0]                  cfg_board_ip;
    wire                         button_hold_active;
    wire                         button_hold_done;
    wire                         button_hold_blink;

    udp_panel_writer udp_inst (
        .clock(clock),
        .reset(reset),
        .button(button),
        .udp_source_valid(udp_source_valid),
        .udp_source_last(udp_source_last),
        .udp_source_ready(udp_source_ready),
        .udp_source_src_port(udp_source_src_port),
        .udp_source_dst_port(udp_source_dst_port),
        .udp_source_ip_address(udp_source_ip_address),
        .udp_source_length(udp_source_length),
        .udp_source_data(udp_source_data),
        .udp_source_error(udp_source_error),
        .ctrl_en(ctrl_en),
        .ctrl_wr(ctrl_wr),
        .ctrl_addr(ctrl_addr),
        .ctrl_wdat(ctrl_wdat),
        .led_reg(udp_led),
        .packet_recv_toggle(packet_recv_toggle),
        .cfg_phys_port_flat(cfg_phys_port_flat),
        .cfg_panel_type_flat(cfg_panel_type_flat),
        .cfg_max_active_y_flat(cfg_max_active_y_flat),
        .cfg_start_active_x_flat(cfg_start_active_x_flat),
        .cfg_board_ip(cfg_board_ip),
        .button_hold_active(button_hold_active),
        .button_hold_done(button_hold_done),
        .button_hold_blink(button_hold_blink)
    );

    // Unpack config wires
    wire [3:0] cfg_phys_port [0:`NUM_ACTIVE_PORTS-1];
    wire [1:0] cfg_panel_type [0:`NUM_ACTIVE_PORTS-1];
    wire [5:0] cfg_max_active_y [0:`NUM_ACTIVE_PORTS-1];
    wire [7:0] cfg_start_active_x [0:`NUM_ACTIVE_PORTS-1];

    genvar c_idx;
    generate
        for (c_idx = 0; c_idx < `NUM_ACTIVE_PORTS; c_idx = c_idx + 1) begin : unpack_cfg
            assign cfg_phys_port[c_idx]      = cfg_phys_port_flat[4*c_idx +: 4];
            assign cfg_panel_type[c_idx]     = cfg_panel_type_flat[2*c_idx +: 2];
            assign cfg_max_active_y[c_idx]   = cfg_max_active_y_flat[6*c_idx +: 6];
            assign cfg_start_active_x[c_idx] = cfg_start_active_x_flat[8*c_idx +: 8];
        end
    endgenerate

    // Heartbeat Activity LED
    reg [23:0] osc_cnt = 0;
    always @(posedge osc25m) begin
        osc_cnt <= osc_cnt + 1;
    end

    wire dhcp_mode_active = (cfg_board_ip == 32'h00000502) || // 0.0.5.2 (binary fields for 101 and 010)
                            (cfg_board_ip == 32'h0000650a) || // 0.0.101.10 (decimal fields for 101 and 10)
                            (cfg_board_ip == 32'h0000002a) || // 0.0.0.42 (decimal 42 in last octet)
                            (cfg_board_ip == 32'h00002a00) || // 0.0.42.0 (decimal 42 in third octet)
                            (cfg_board_ip == 32'h00002a2a) || // 0.0.42.42
                            (cfg_board_ip == 32'h2a2a2a2a);   // 42.42.42.42
    wire dhcp_led_pattern = (osc_cnt[23:21] == 3'd0 || osc_cnt[23:21] == 3'd2) ? 1'b0 : 1'b1;

    assign led = button_hold_active ? (button_hold_done ? 1'b0 : button_hold_blink) :
                 dhcp_mode_active   ? dhcp_led_pattern :
                                      (locked ? ~osc_cnt[23] : 1'b0);

    genvar panel_index;

    // Driver outputs
    wire [`NUM_ACTIVE_PORTS-1:0] panel_out_r0;
    wire [`NUM_ACTIVE_PORTS-1:0] panel_out_g0;
    wire [`NUM_ACTIVE_PORTS-1:0] panel_out_b0;
    wire [`NUM_ACTIVE_PORTS-1:0] panel_out_r1;
    wire [`NUM_ACTIVE_PORTS-1:0] panel_out_g1;
    wire [`NUM_ACTIVE_PORTS-1:0] panel_out_b1;

    wire [`NUM_ACTIVE_PORTS-1:0] A_int;
    wire [`NUM_ACTIVE_PORTS-1:0] B_int;
    wire [`NUM_ACTIVE_PORTS-1:0] C_int;
    wire [`NUM_ACTIVE_PORTS-1:0] D_int;
    wire [`NUM_ACTIVE_PORTS-1:0] E_int;
    wire [`NUM_ACTIVE_PORTS-1:0] LAT_int;
    wire [`NUM_ACTIVE_PORTS-1:0] OE_int;
    wire [`NUM_ACTIVE_PORTS-1:0] CLK_int;

    generate
        for (panel_index = 0; panel_index < `NUM_ACTIVE_PORTS; panel_index = panel_index + 1) begin : panel_gen
            ledpanel panel_inst (
                .ctrl_clk(clock),
                .ctrl_en(ctrl_en[panel_index]),
                .ctrl_wr(ctrl_wr),
                .ctrl_addr(ctrl_addr),
                .ctrl_wdat(ctrl_wdat),

                .display_clock(display_clock),
                
                // Runtime configs
                .panel_type(cfg_panel_type[panel_index]),
                .max_active_y(cfg_max_active_y[panel_index]),
                .start_active_x(cfg_start_active_x[panel_index]),

                .panel_r0(panel_out_r0[panel_index]),
                .panel_g0(panel_out_g0[panel_index]),
                .panel_b0(panel_out_b0[panel_index]),
                .panel_r1(panel_out_r1[panel_index]),
                .panel_g1(panel_out_g1[panel_index]),
                .panel_b1(panel_out_b1[panel_index]),
                
                .panel_a(A_int[panel_index]),
                .panel_b(B_int[panel_index]),
                .panel_c(C_int[panel_index]),
                .panel_d(D_int[panel_index]),
                .panel_e(E_int[panel_index]),
                .panel_clk(CLK_int[panel_index]),
                .panel_stb(LAT_int[panel_index]),
                .panel_oe(OE_int[panel_index])
            );
        end
    endgenerate

    //------------------------------------------------------------------
    // Crossbar Multiplexer Routing Logic
    //------------------------------------------------------------------

    genvar phys_port_idx;
    generate
        for (phys_port_idx = 0; phys_port_idx < 16; phys_port_idx = phys_port_idx + 1) begin : gen_crossbar
            reg r0_reg, g0_reg, b0_reg, r1_reg, g1_reg, b1_reg;
            integer l_idx;
            
            always @(*) begin
                r0_reg = 1'b0;
                g0_reg = 1'b0;
                b0_reg = 1'b0;
                r1_reg = 1'b0;
                g1_reg = 1'b0;
                b1_reg = 1'b0;
                for (l_idx = 0; l_idx < `NUM_ACTIVE_PORTS; l_idx = l_idx + 1) begin
                    if (cfg_phys_port[l_idx] == phys_port_idx[3:0]) begin
                        r0_reg = r0_reg | panel_out_r0[l_idx];
                        g0_reg = g0_reg | panel_out_g0[l_idx];
                        b0_reg = b0_reg | panel_out_b0[l_idx];
                        r1_reg = r1_reg | panel_out_r1[l_idx];
                        g1_reg = g1_reg | panel_out_g1[l_idx];
                        b1_reg = b1_reg | panel_out_b1[l_idx];
                    end
                end
            end

            assign R0[phys_port_idx] = r0_reg;
            assign G0[phys_port_idx] = g0_reg;
            assign B0[phys_port_idx] = b0_reg;
            assign R1[phys_port_idx] = r1_reg;
            assign G1[phys_port_idx] = g1_reg;
            assign B1[phys_port_idx] = b1_reg;
        end
    endgenerate

    //------------------------------------------------------------------
    // Synchronize packet_recv_toggle to display_clock (52 MHz) Watchdog
    //------------------------------------------------------------------

    reg packet_recv_sync0 = 1'b0;
    reg packet_recv_sync1 = 1'b0;
    reg packet_recv_sync2 = 1'b0;
    always @(posedge display_clock) begin
        packet_recv_sync0 <= packet_recv_toggle;
        packet_recv_sync1 <= packet_recv_sync0;
        packet_recv_sync2 <= packet_recv_sync1;
    end
    wire packet_recv_edge = (packet_recv_sync1 != packet_recv_sync2);

    // Watchdog Counter (52 MHz clock domain: 26,000,000 ticks = 0.5s timeout)
    reg [24:0] watchdog_cnt = 25'd26000000;
    reg no_signal = 1'b1;

    always @(posedge display_clock) begin
        if (packet_recv_edge) begin
            watchdog_cnt <= 0;
            no_signal    <= 1'b0;
        end else if (watchdog_cnt < 25'd26000000) begin
            watchdog_cnt <= watchdog_cnt + 1'b1;
            no_signal    <= 1'b0;
        end else begin
            no_signal    <= 1'b1;
        end
    end

    // Use logical port 0 outputs for the shared timing signals
    assign A = A_int[0];
    assign B = B_int[0];
    assign C = C_int[0];
    assign D = D_int[0];
    assign E = E_int[0];
    assign LAT = LAT_int[0];
    assign OE  = no_signal ? 1'b1 : OE_int[0];
    assign CLK = CLK_int[0];

endmodule
