#!/bin/bash
# Launch the real 32-bit LEDVISION GUI under Wine on :99 (headless), prefix root-owned.
set -u
export DISPLAY=:99
export WINEPREFIX=/home/muse/Desktop/LED/.wine-led
export HOME=/root
export WINEDEBUG=-all
cd /home/muse/Desktop/LED/.wine-led/drive_c/LEDVISION || exit 2
nohup wine LEDVISION.exe >/tmp/ledvision.log 2>&1 &
echo "launched wine LEDVISION.exe pid=$!"
sleep 1
echo "done"
