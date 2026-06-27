#!/usr/bin/env bash
# Run probe.exe under the win64 prefix while capturing Colorlight L2 on enx.
# Arg1 (optional) "save" -> also attempt SaveToDevice (step 4). Must run as root.
set -u
IF=enx9c69d388d76e
TS=$(date +%s)
PCAP=/home/muse/Desktop/LED/re/capture/probe_$TS.pcap
LOG=/home/muse/Desktop/LED/re/wine/probe_$TS.log
export WINEPREFIX=/home/muse/Desktop/LED/.wine-led64 WINEARCH=win64 HOME=/root WINEDEBUG=-all
cd /home/muse/Desktop/LED/.wine-led64/drive_c/LEDSetting/x64/Bin

tcpdump -i "$IF" -w "$PCAP" -s 0 'not arp and not ip and not ip6' 2>/dev/null &
TD=$!
sleep 1
echo "=== probe args: $* ===" > "$LOG"
timeout 40 wine probe.exe "$@" >>"$LOG" 2>/dev/null
RC=$?
echo "(wine rc=$RC, 124=timeout)" >> "$LOG"
sleep 1
kill $TD 2>/dev/null; wait $TD 2>/dev/null
wineserver -k 2>/dev/null
echo "----- probe stdout -----"; cat "$LOG"
echo "----- capture ($PCAP) -----"
tcpdump -r "$PCAP" -nn -e -c 40 2>/dev/null
echo "frame_count=$(tcpdump -r "$PCAP" -nn 2>/dev/null | wc -l)"
echo "PCAPFILE=$PCAP"
