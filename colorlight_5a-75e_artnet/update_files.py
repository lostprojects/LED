# Update top.v
with open('./top.v', 'r') as f:
    top_content = f.read()

old_counter = '''    // Power-on reset circuit (generates a ~42ms reset pulse)
    reg [20:0] rst_counter = 0;
    reg        phy_rst_n = 1'b0;

    always @(posedge clk_25m) begin
        if (rst_counter < 21'h0FFFFF) begin
            rst_counter <= rst_counter + 1;
            phy_rst_n   <= 1'b0; // Hold reset active-low
        end else begin
            phy_rst_n   <= 1'b1; // Release reset
        end
    end'''

new_counter = '''    // Power-on reset circuit (generates a ~42ms reset pulse, resettable via btn_n)
    reg [20:0] rst_counter = 0;
    reg        phy_rst_n = 1'b0;

    always @(posedge clk_25m) begin
        if (!btn_n) begin
            rst_counter <= 0;
            phy_rst_n   <= 1'b0;
        end else if (rst_counter < 21'h0FFFFF) begin
            rst_counter <= rst_counter + 1;
            phy_rst_n   <= 1'b0; // Hold reset active-low
        end else begin
            phy_rst_n   <= 1'b1; // Release reset
        end
    end'''

top_content = top_content.replace(old_counter, new_counter)
top_content = top_content.replace('.rst_n(btn_n),', '.rst_n(phy_rst_n),')

with open('./top.v', 'w') as f:
    f.write(top_content)

# Update colorlight.lpf
with open('./colorlight.lpf', 'r') as f:
    lpf_content = f.read()

lpf_content = lpf_content.replace(
    'IOBUF PORT "btn_n" IO_TYPE=LVCMOS33;',
    'IOBUF PORT "btn_n" IO_TYPE=LVCMOS33 PULLMODE=UP;'
)

with open('./colorlight.lpf', 'w') as f:
    f.write(lpf_content)

print("Files updated successfully!")
