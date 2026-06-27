#!/bin/bash
# Bring up a headless X display :99 + openbox WM (NEVER :0 — CEF crashes the desktop).
set -u
export DISPLAY=:99
RES="${RES:-1920x1080x24}"

# clear any stale lock for :99
rm -f /tmp/.X99-lock 2>/dev/null
rm -f /tmp/.X11-unix/X99 2>/dev/null

# start Xvfb if not already up
if ! pgrep -f "Xvfb :99" >/dev/null; then
  nohup Xvfb :99 -screen 0 "$RES" -ac +extension RANDR >/tmp/xvfb99.log 2>&1 &
  sleep 2
fi

# start openbox if not already up on :99
if ! pgrep -f "openbox" >/dev/null; then
  nohup openbox >/tmp/openbox99.log 2>&1 &
  sleep 1
fi

echo "=== :99 status ==="
pgrep -fa "Xvfb :99"
pgrep -fa openbox
DISPLAY=:99 xdotool getdisplaygeometry 2>&1 || echo "xdotool can't reach :99 yet"
