#!/usr/bin/env bash
# Compile + run h4.exe under the win32 LEDVISION prefix, capturing Colorlight L2 on enx.
# Run as root (pcap). Args pass through: e4 e5 (the two CreateScreen enums, 0..3).
set -u
IF=enx9c69d388d76e
TS=$(date +%s)
PCAP=/home/muse/Desktop/LED/re/capture/h4_$TS.pcap
LOG=/home/muse/Desktop/LED/re/wine/h4_$TS.log
SRC=/home/muse/Desktop/LED/re/wine/h4.c
EXE=/home/muse/Desktop/LED/.wine-led/drive_c/LEDVISION/h4.exe

# clear any stray captures from earlier runs so wait/kill can't hang
pkill -x tcpdump 2>/dev/null; sleep 1

i686-w64-mingw32-gcc -O0 -o "$EXE" "$SRC" 2>"$LOG.cc" || { echo "COMPILE FAILED"; cat "$LOG.cc"; exit 1; }

export WINEPREFIX=/home/muse/Desktop/LED/.wine-led WINEARCH=win32 HOME=/root WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
cd /home/muse/Desktop/LED/.wine-led/drive_c/LEDVISION

tcpdump -i "$IF" -w "$PCAP" -s 0 'not arp and not ip and not ip6' >/dev/null 2>&1 &
TD=$!
sleep 1
echo "=== h4 args: $* ===" | tee "$LOG"
timeout 30 wine h4.exe "$@" >>"$LOG" 2>/dev/null
echo "(wine rc=$?)" >>"$LOG"
sleep 1
kill -INT "$TD" 2>/dev/null
timeout 5 wait "$TD" 2>/dev/null
pkill -x tcpdump 2>/dev/null
timeout 8 wineserver -k 2>/dev/null
echo "----- h4 stdout -----"; cat "$LOG"
echo "----- capture: Colorlight L2 frames -----"
tcpdump -r "$PCAP" -nn -e 2>/dev/null | head -40
echo "frame_count=$(tcpdump -r "$PCAP" -nn 2>/dev/null | wc -l)"
echo "PCAPFILE=$PCAP"
