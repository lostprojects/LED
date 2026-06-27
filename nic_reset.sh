#!/usr/bin/env bash
# Wake up the Mac mini's built-in Broadcom (tg3) Ethernet port enp4s0.
# Safe: internet is on the USB WiFi, so reloading tg3 won't drop your connection.
# Run once:   sudo bash /home/muse/Desktop/LED/nic_reset.sh
set -u
IF=enp4s0

say(){ echo -e "\n=== $* ==="; }

say "BEFORE"
echo "carrier=$(cat /sys/class/net/$IF/carrier 2>/dev/null) speed=$(cat /sys/class/net/$IF/speed 2>/dev/null) operstate=$(cat /sys/class/net/$IF/operstate 2>/dev/null)"

say "1) admin down/up"
ip link set $IF down; sleep 1; ip link set $IF up; sleep 4
echo "carrier=$(cat /sys/class/net/$IF/carrier) speed=$(cat /sys/class/net/$IF/speed)"

if [ "$(cat /sys/class/net/$IF/carrier)" != "1" ]; then
  say "2) reload tg3 driver"
  modprobe -r tg3 && sleep 1 && modprobe tg3 && sleep 6
  ip link set $IF up 2>/dev/null; sleep 3
  echo "carrier=$(cat /sys/class/net/$IF/carrier) speed=$(cat /sys/class/net/$IF/speed)"
fi

say "3) force autoneg / try fixed 100M as a probe (then back to auto)"
ethtool -r $IF 2>/dev/null; sleep 3
echo "after re-negotiate: carrier=$(cat /sys/class/net/$IF/carrier) speed=$(cat /sys/class/net/$IF/speed)"

say "KERNEL LINK MESSAGES (last 25)"
dmesg | grep -iE "tg3|$IF|Link is" | tail -25

say "ETHTOOL"
ethtool $IF 2>/dev/null | grep -iE "link detected|speed|duplex|auto-neg"

say "RESULT"
if [ "$(cat /sys/class/net/$IF/carrier)" = "1" ]; then
  echo ">>> LINK UP. The port works now."
else
  echo ">>> STILL NO LINK after reset. Likely a hardware/port issue."
  echo ">>> Next: try a USB-to-Ethernet adapter to drive the panels instead."
fi
