#!/usr/bin/env python3
"""
colorlight_stock_test.py — light a panel via the STOCK Colorlight protocol.

No flashing. Sends Colorlight L2 frames (brightness + 0x55 pixel rows + 0x0107
sync) to the receiver card to display test patterns.

  sudo python3 colorlight_stock_test.py <iface> [W] [H] [brightness]
  e.g. sudo python3 colorlight_stock_test.py enx9c69d388d76e 64 64 64

Frame layout from FalconChristmas/fpp ColorLight-5a-75.cpp:
  dst MAC 11:22:33:44:55:66, src 22:22:33:44:55:66
  pixel row (ethertype 0x5500): data[0:2]=row, [2:4]=pixel offset,
      [4:6]=pixels-in-packet, [6]=0x08 [7]=0x88, then RGB bytes
  sync (0x0107): data[0]=0x07, [22]=brightness, [23]=0x05, [25..27]=brightness
  brightness (0x0a00): data[0..2]=brightness, data[3]=0xff
"""
import socket, struct, sys, time

IFACE = sys.argv[1] if len(sys.argv) > 1 else "enx9c69d388d76e"
W     = int(sys.argv[2]) if len(sys.argv) > 2 else 64
H     = int(sys.argv[3]) if len(sys.argv) > 3 else 64
BRIGHT= int(sys.argv[4]) if len(sys.argv) > 4 else 64      # 0-255, 64 ~= 25%

DST = b"\x11\x22\x33\x44\x55\x66"
SRC = b"\x22\x22\x33\x44\x55\x66"

def frame(etype, payload):
    return DST + SRC + etype + payload

def brightness_pkt(b):
    d = bytearray(64)
    d[0] = d[1] = d[2] = b
    d[3] = 0xff
    return frame(b"\x0a\x00", bytes(d))

def sync_pkt(b):
    d = bytearray(99)
    d[0]  = 0x07
    d[22] = b
    d[23] = 0x05
    d[25] = d[26] = d[27] = b
    return frame(b"\x01\x07", bytes(d))

def row_pkt(row, pixels_rgb):
    n = len(pixels_rgb) // 3
    hdr = bytes([row >> 8, row & 0xff, 0, 0, n >> 8, n & 0xff, 0x08, 0x88])
    return frame(b"\x55\x00", hdr + pixels_rgb)

def send_framebuffer(sock, fb, b):
    sock.send(brightness_pkt(b))
    for row in range(H):
        line = fb[row * W * 3:(row + 1) * W * 3]
        sock.send(row_pkt(row, line))
    sock.send(sync_pkt(b))

def solid(r, g, b):
    return bytes([r, g, b]) * (W * H)

def bars():
    cols = [(255,0,0),(0,255,0),(0,0,255),(255,255,0),(0,255,255),(255,0,255),(255,255,255),(40,40,40)]
    fb = bytearray()
    for y in range(H):
        for x in range(W):
            fb += bytes(cols[(x * len(cols)) // W])
    return bytes(fb)

def quadrants():
    fb = bytearray()
    for y in range(H):
        for x in range(W):
            top = y < H // 2; left = x < W // 2
            fb += bytes((255,0,0) if (top and left) else (0,255,0) if (top and not left)
                        else (0,0,255) if (not top and left) else (255,255,255))
    return bytes(fb)

PATTERNS = [
    ("RED   (expect whole panel red)",    solid(255,0,0)),
    ("GREEN (expect whole panel green)",  solid(0,255,0)),
    ("BLUE  (expect whole panel blue)",   solid(0,0,255)),
    ("WHITE",                              solid(255,255,255)),
    ("COLOR BARS (R G B Y C M W grey L>R)", bars()),
    ("QUADRANTS (TL red TR green BL blue BR white)", quadrants()),
]

def main():
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    s.bind((IFACE, 0))
    print("Sending on %s  %dx%d  brightness=%d" % (IFACE, W, H, BRIGHT))
    print("Each pattern shows ~3s. Watch the panel.\n")
    try:
        for name, fb in PATTERNS:
            print("  -> %s" % name)
            t = time.time()
            while time.time() - t < 3.0:      # resend ~continuously to hold it
                send_framebuffer(s, fb, BRIGHT)
                time.sleep(0.04)              # ~25 fps
        print("\nDone. (Panel may blank shortly — stock card watchdog.)")
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        s.close()

if __name__ == "__main__":
    main()
