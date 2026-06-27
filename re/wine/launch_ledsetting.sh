#!/bin/bash
# Launch the x64 LEDSetting GUI under the win64 prefix on :99.
set -u
export DISPLAY=:99
export WINEPREFIX=/home/muse/Desktop/LED/.wine-led64
export HOME=/root
export WINEDEBUG=-all
cd /home/muse/Desktop/LED/.wine-led64/drive_c/LEDSetting/x64/Bin || exit 2
nohup wine LEDSetting.exe >/tmp/ledsetting.log 2>&1 &
echo "launched LEDSetting.exe pid=$!"
sleep 1
echo done
