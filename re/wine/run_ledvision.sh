#!/usr/bin/env bash
# Launch LEDVISION GUI under Wine (Plan A, run as root for pcap, render to user's X).
export WINEPREFIX=/home/muse/Desktop/LED/.wine-led
export WINEARCH=win32
export DISPLAY=:0
export XAUTHORITY=/home/muse/.Xauthority
export HOME=/root
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
export WINEDEBUG=-all
cd /home/muse/Desktop/LED/.wine-led/drive_c/LEDVISION
exec wine LEDVISION.exe
