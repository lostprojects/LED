#!/usr/bin/env bash
# Create the 32-bit Wine prefix for running LEDVISION (Plan A).
# Run as root (pcap needs it) but render to the user's X session.
set -euo pipefail

export WINEPREFIX=/home/muse/Desktop/LED/.wine-led
export WINEARCH=win32
export DISPLAY=:0
export XAUTHORITY=/home/muse/.Xauthority
# Skip Mono/Gecko auto-download dialogs; we don't need .NET or an embedded browser.
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
export WINEDEBUG=-all

echo "[*] WINEPREFIX=$WINEPREFIX  ARCH=$WINEARCH"
wineboot -u
wineserver -w
echo "[*] prefix booted"
ls -la "$WINEPREFIX/drive_c" || true
