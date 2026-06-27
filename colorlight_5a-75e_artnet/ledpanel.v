// Generic Configurable LED Panel Driver
// Supporting variable color depths and runtime layout configurations
// (Panel scan rows, shift columns, and stacked panel mappings).

`default_nettype none
`include "config.vh"

module ledpanel (
    input wire ctrl_clk,
    input wire ctrl_en,
    input wire [3:0] ctrl_wr,           // Write enable (active high)
    input wire [15:0] ctrl_addr,        // Addr to write color info on [col_info][row_info]
    input wire [23:0] ctrl_wdat,        // Data to be written [R][G][B] (8-bit per channel)

    input wire display_clock,
    
    // Runtime Config Inputs
    input wire [1:0] panel_type,        // 0 = 64x64 (1/32), 1 = Stacked 32x64 (1/16), 2 = Standard 1/16
    input wire [5:0] max_active_y,      // row steps before blanking (e.g. 32 for 1/32, 16 for 1/16)
    input wire [7:0] start_active_x,    // column shift offset (e.g. 64 for 64-col panel, 96 for 32-col)

    output reg panel_r0, panel_g0, panel_b0, panel_r1, panel_g1, panel_b1,
    output reg panel_a, panel_b, panel_c, panel_d, panel_e, panel_clk, panel_stb, panel_oe
);

  parameter integer INPUT_DEPTH          = 6;    // bits of color before gamma correction
  parameter integer COLOR_DEPTH          = `COLOR_DEPTH;
  parameter integer CHAINED              = 1;

  localparam integer SCAN_CHAINED        = 2; // Always scan 128 columns for lockstep

  // Unified video memory storing [R][G][B] combined to optimize Block RAM usage
  reg [3*COLOR_DEPTH-1:0] video_mem [0:CHAINED*4096-1];
  reg [COLOR_DEPTH-1:0]   gamma_mem [0:2**COLOR_DEPTH-1];

  initial begin
        panel_a <= 0;
        panel_b <= 0;
        panel_c <= 0;
        panel_d <= 0;
        panel_e <= 0;
        if (COLOR_DEPTH == 6) begin
            $readmemh("6bit_to_6bit_gamma.mem", gamma_mem);
        end else begin
            $readmemh("6bit_to_8bit_gamma.mem", gamma_mem); // fallback / mapping to 8-bit output
        end
        // Note: We omit the large video_mem zeroing loop to speed up synthesis compile times.
        // Block RAMs are initialized to zero by the FPGA configuration process anyway.
  end

  // Write side logic: pack R, G, B channels into unified video_mem
  always @(posedge ctrl_clk) begin
        if (ctrl_en && ctrl_wr != 4'b0000) begin
            video_mem[ctrl_addr] <= {
                ctrl_wdat[16+COLOR_DEPTH-1:16], // R
                ctrl_wdat[8+COLOR_DEPTH-1:8],   // G
                ctrl_wdat[0+COLOR_DEPTH-1:0]    // B
            };
        end
  end

  reg [12:0] cnt_x = 0;
  reg [4:0]  cnt_y = 0;
  reg [2:0]  cnt_z = 0;
  reg        state = 0;

  reg [2:0]  addr_z;
  reg [2:0]  data_rgb;
  reg [2:0]  data_rgb_q;
  reg [12:0] max_cnt_x;

  always @(posedge display_clock) begin
      case (cnt_z)
          0: max_cnt_x = 64*SCAN_CHAINED+8;
          1: max_cnt_x = 128*SCAN_CHAINED;
          2: max_cnt_x = 256*SCAN_CHAINED;
          3: max_cnt_x = 512*SCAN_CHAINED;
          4: max_cnt_x = 1024*SCAN_CHAINED;
          5: max_cnt_x = 2048*SCAN_CHAINED;
          6: max_cnt_x = 4096*SCAN_CHAINED;
          7: max_cnt_x = 8192*CHAINED;
      endcase
  end

  always @(posedge display_clock) begin
      state <= !state;
      if (!state) begin
          if (cnt_x > max_cnt_x) begin
              cnt_x <= 0;
              cnt_z <= cnt_z + 1;
              if (cnt_z == COLOR_DEPTH-1) begin
                  cnt_y <= cnt_y + 1;
                  cnt_z <= 0;
              end
          end else begin
              cnt_x <= cnt_x + 1;
          end
      end
  end

  always @(posedge display_clock) begin
      panel_oe <= 64*SCAN_CHAINED-8 < cnt_x && cnt_x < 64*SCAN_CHAINED+8;
      if (state) begin
          panel_clk <= 1 < cnt_x && cnt_x < 64*SCAN_CHAINED+2;
          panel_stb <= cnt_x == 64*SCAN_CHAINED+2;
      end else begin
          panel_clk <= 0;
          panel_stb <= 0;
      end
  end

  reg [3*COLOR_DEPTH-1:0] val_rgb;

  wire [5:0] read_row;
  wire       out_en;
  wire [5:0] read_col = (panel_type == 3) ? {!cnt_x[6], cnt_x[4:0]} :
                        (panel_type == 2 && start_active_x == 96) ? {1'b0, cnt_x[4:0]} :
                        cnt_x[5:0];

  // Row coordinate mapping selector based on panel type
  assign read_row = (panel_type == 0) ? (cnt_y + 6'd32*(!state)) : // 64x64 (1/32)
                    (panel_type == 1) ? (                          // Stacked/Chained 32x64
                        (cnt_y >= 16) ? 6'd0 :
                        (cnt_x < 64) ? (cnt_y + 6'd32 + 6'd16*(!state)) : // bottom panel
                        (cnt_y + 6'd16*(!state))                         // top panel
                    ) :
                    (panel_type == 3) ? (                          // Stacked/Chained 32x32 (4 panels)
                        (cnt_y >= 16) ? 6'd0 :
                        cnt_x[5] ? (cnt_y + 6'd16*(!state)) :
                                   (cnt_y + 6'd32 + 6'd16*(!state))
                    ) :
                    (cnt_y + 6'd16*(!state));                      // Standard 1/16 scan panels

  // Blanking control: active only when row count is valid and shift count is in active region
  assign out_en = (cnt_y < max_active_y) && (cnt_x >= start_active_x);

  always @(posedge display_clock) begin
      val_rgb <= out_en ? video_mem[{read_row, read_col}] : {3*COLOR_DEPTH{1'b0}};
      addr_z  <= cnt_z;
  end

  always @(posedge display_clock) begin
      data_rgb[2] <= gamma_mem[val_rgb[3*COLOR_DEPTH-1 : 2*COLOR_DEPTH]][addr_z];
      data_rgb[1] <= gamma_mem[val_rgb[2*COLOR_DEPTH-1 : COLOR_DEPTH]][addr_z];
      data_rgb[0] <= gamma_mem[val_rgb[COLOR_DEPTH-1 : 0]][addr_z];
  end

  always @(posedge display_clock) begin
      data_rgb_q <= data_rgb;
      if (!state) begin
          if (0 < cnt_x && cnt_x < 64*SCAN_CHAINED+1) begin
              {panel_r1, panel_r0} <= {data_rgb[2], data_rgb_q[2]};
              {panel_g1, panel_g0} <= {data_rgb[1], data_rgb_q[1]};
              {panel_b1, panel_b0} <= {data_rgb[0], data_rgb_q[0]};
          end else begin
              {panel_r1, panel_r0} <= 0;
              {panel_g1, panel_g0} <= 0;
              {panel_b1, panel_b0} <= 0;
          end
      end
      else if (cnt_x == 64*SCAN_CHAINED)  begin
          {panel_e, panel_d, panel_c, panel_b, panel_a} <= (panel_type == 0) ? cnt_y : { 1'b0, cnt_y[3:0] };
      end
  end
endmodule
