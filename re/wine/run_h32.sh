#!/usr/bin/env bash
# Run h32.exe under the win32 prefix while capturing Colorlight L2 on enx.
# Must run as root.  Args pass through to h32.exe.
set -u
IF=enx9c69d388d76e
TS=$(date +%s)
PCAP=/home/muse/Desktop/LED/re/capture/h32_$TS.pcap
LOG=/home/muse/Desktop/LED/re/wine/h32_$TS.log
export WINEPREFIX=/home/muse/Desktop/LED/.wine-led WINEARCH=win32 HOME=/root WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
cd /home/muse/Desktop/LED/.wine-led/drive_c/LEDVISION

tcpdump -i "$IF" -w "$PCAP" -s 0 'not arp and not ip and not ip6' 2>/dev/null &
TD=$!
sleep 1
echo "=== h32 args: $* ===" | tee "$LOG"
timeout 30 wine h32.exe "$@" >>"$LOG" 2>/dev/null
echo "(wine rc=$?)" >>"$LOG"
sleep 1
kill $TD 2>/dev/null; wait $TD 2>/dev/null
wineserver -k 2>/dev/null
echo "----- h32 stdout -----"; cat "$LOG"
echo "----- capture summary ($PCAP) -----"
tcpdump -r "$PCAP" -nn -e -c 40 2>/dev/null
echo "frame_count=$(tcpdump -r "$PCAP" -nn 2>/dev/null | wc -l)"
echo "PCAPFILE=$PCAP"
