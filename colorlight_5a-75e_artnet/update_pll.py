with open('./pll_generated.v', 'r') as f:
    c = f.read()
c = c.replace('ENCLKOP(1\'b0)', 'ENCLKOP(1\'b1)')
with open('./pll.v', 'w') as f:
    f.write(c)
