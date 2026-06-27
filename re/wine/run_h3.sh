#!/usr/bin/env bash
# Run h3.exe under the win64 prefix while capturing Colorlight L2 on enx.
# Args passed through to h3.exe.  Must run as root.
set -u
IF=enx9c69d388d76e
TS=$(date +%s)
PCAP=/home/muse/Desktop/LED/re/capture/h3_$TS.pcap
LOG=/home/muse/Desktop/LED/re/wine/h3_$TS.log
export WINEPREFIX=/home/muse/Desktop/LED/.wine-led64 WINEARCH=win64 HOME=/root WINEDEBUG=-all
cd /home/muse/Desktop/LED/.wine-led64/drive_c/LEDSetting/x64/Bin

tcpdump -i "$IF" -w "$PCAP" -s 0 'not arp and not ip and not ip6' 2>/dev/null &
TD=$!
sleep 1
echo "=== h3 args: $* ===" | tee "$LOG"
timeout 25 wine h3.exe "$@" >>"$LOG" 2>/dev/null
RC=$?
echo "(wine rc=$RC, 124=timeout)" | tee -a "$LOG"
sleep 1
kill $TD 2>/dev/null; wait $TD 2>/dev/null
wineserver -k 2>/dev/null
echo "----- h3 stdout -----"; cat "$LOG"
echo "----- capture ($PCAP) -----"
tcpdump -r "$PCAP" -nn -e -c 30 2>/dev/null
echo "frame_count=$(tcpdump -r "$PCAP" -nn 2>/dev/null | wc -l)"
echo "PCAPFILE=$PCAP"
