#!/usr/bin/env python3
"""
bringup_test.py - end-to-end attempt: configure the 5A-75E from a .rcvp, then
stream test pixels, using the frame layout decoded from re/data_emu.txt
(Colorlight's own auto-generated receiver-input sim = authoritative wire bytes).

KEY DIFFERENCE vs colorlight_stock_test.py:
  data_emu.txt shows the DISPLAY frame as, starting at ethernet byte 12:
      byte12      0x55          (command = display data)
      byte13..14  row (u16, BE)
      byte15..16  column start (u16, BE)
      byte17..18  pixel count (u16, BE)
      byte19      0x08
      byte20      0x88
      byte21..    RGB bytes
  i.e. there is NO second ethertype byte before the row. The old FPP-derived
  sender used ethertype 0x5500 then row at byte14, shifting every field +1.
  This sender follows data_emu.txt exactly.

  Config frames (also from data_emu.txt), starting at byte 12:
      byte12      command (0x05 basic / 0x03 route / 0x02 cardarea / 0xFF init)
      byte13..14  serial (u16, BE) = 0
      byte15      subframe = 0,1,..
      byte16..    payload

USAGE
  sudo python3 bringup_test.py <iface> <rcvp> [seconds]
  e.g. sudo python3 bringup_test.py enx9c69d388d76e \
       "re/config_files/General Parameters(Fullcolor)/26- full-color thirty-two scan.rcvp" 30
Watch the panel. Ctrl-C to stop.
"""
import socket, struct, sys, time
import config_sender as cs   # reuse the .rcvp parser + frame builder

IFACE = sys.argv[1] if len(sys.argv) > 1 else "enx9c69d388d76e"
RCVP  = sys.argv[2] if len(sys.argv) > 2 else None
SECS  = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0

DST = b"\x11\x22\x33\x44\x55\x66"
SRC = b"\x22\x22\x33\x44\x55\x66"
W, H = 64, 64
BRIGHT = 80


def open_sock():
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    s.bind((IFACE, 0)); s.settimeout(0.3)
    return s


# ---- config frames -----------------------------------------------------------
def init_frame():
    """0xFF init frame, payload approximated from data_emu.txt first frame:
    bytes16+: 00*5, 0x40, 0x02, then zeros (0x40=64 looks like width)."""
    payload = bytes([0]*5 + [0x40, 0x02] + [0]*(0x0a))
    return DST + SRC + bytes([0xFF, 0, 0, 0]) + payload


def config_frames(rcvp_path):
    data = open(rcvp_path, "rb").read()
    p = cs.parse_rcvp(data)
    frames = [init_frame()]
    frames += cs.build_frames(0x05, p["basic_params"])
    for sec in p["sections"]:
        cmd = cs.IDX_TO_CMD.get(sec["idx"], sec["idx"])
        frames += cs.build_frames(cmd, sec["payload"])
    return frames, p


# ---- display frames (data_emu.txt layout) ------------------------------------
def brightness_frame(b):
    d = bytearray(64); d[0] = d[1] = d[2] = b; d[3] = 0xff
    return DST + SRC + b"\x0a\x00" + bytes(d)


def row_frame(row, rgb):
    n = len(rgb) // 3
    hdr = bytes([0x55, row >> 8, row & 0xff, 0, 0, n >> 8, n & 0xff, 0x08, 0x88])
    fr = DST + SRC + hdr + rgb
    if len(fr) < 60: fr += b"\x00" * (60 - len(fr))
    return fr


def sync_frame(b):
    d = bytearray(99); d[0] = 0x07; d[22] = b; d[23] = 0x05
    d[25] = d[26] = d[27] = b
    return DST + SRC + b"\x01\x07" + bytes(d)


def push_fb(s, fb, b):
    s.send(brightness_frame(b))
    for row in range(H):
        s.send(row_frame(row, fb[row*W*3:(row+1)*W*3]))
    s.send(sync_frame(b))


def solid(r, g, b): return bytes([r, g, b]) * (W * H)


def main():
    s = open_sock()
    if RCVP:
        frames, p = config_frames(RCVP)
        print("Config: %d frames (init + basic + %d sections), panel %dx%d scan %d"
              % (len(frames), len(p["sections"]), p["width"], H, p["scan"]))
    else:
        frames = []
        print("No .rcvp given - pixel-only test")

    patterns = [("WHITE", solid(255,255,255)), ("RED", solid(255,0,0)),
                ("GREEN", solid(0,255,0)), ("BLUE", solid(0,0,255))]
    print("Sending config then cycling colours for %.0fs. WATCH THE PANEL.\n" % SECS)
    t0 = time.time(); pi = 0; last_cfg = 0
    try:
        while time.time() - t0 < SECS:
            # (re)send config ~every 2s in case it is volatile / needs reassert
            if frames and time.time() - last_cfg > 2.0:
                for fr in frames:
                    s.send(fr)
                last_cfg = time.time()
            name, fb = patterns[pi % len(patterns)]
            tp = time.time()
            while time.time() - tp < 2.0 and time.time() - t0 < SECS:
                push_fb(s, fb, BRIGHT)
                time.sleep(0.04)
            print("  showing %s" % name)
            pi += 1
    except KeyboardInterrupt:
        print("stopped")
    s.close()


if __name__ == "__main__":
    main()
