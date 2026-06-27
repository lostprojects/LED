#!/bin/bash
set -e
cd "$(dirname "$0")"
source ~/oss-cad-suite/environment
echo "=== Synthesizing with Yosys ==="
yosys -s syn.ys -o top.json
echo "=== Routing with nextpnr-ecp5 ==="
nextpnr-ecp5 --pre-pack clocks.py --25k --freq 125 --timing-allow-fail --package CABGA256 --speed 6 --json top.json --lpf top.lpf --write top-post-route.json --textcfg top.config
echo "=== Packing bitstream with ecppack ==="
ecppack --compress top.config top.bit
echo "=== Build Complete ==="
