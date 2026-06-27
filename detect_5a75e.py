#!/usr/bin/env python3
"""
detect_5a75e.py — find and talk to a STOCK Colorlight 5A-75E over raw Ethernet.

Does NOT flash or modify the card. It:
  1. checks the link on the chosen NIC,
  2. broadcasts the Colorlight 0x0700 detection frame,
  3. listens for the card's 0x0805 reply and decodes firmware / configured
     cabinet size / uptime / packet count,
  4. passively dumps any other frames so we can ID the card's MAC even if the
     decode offsets differ on this firmware.

Run as root (raw sockets):  sudo python3 detect_5a75e.py enp4s0

Protocol refs: FalconChristmas/fpp ColorLight-5a-75.cpp, hkubota colorlight.
"""
import socket
import struct
import sys
import time

IFACE = sys.argv[1] if len(sys.argv) > 1 else "enp4s0"

ETH_P_ALL = 0x0003
CARD_MAC   = b"\x11\x22\x33\x44\x55\x66"   # detection destination (card)
SENDER_MAC = b"\x22\x22\x33\x44\x55\x66"   # our source MAC (Colorlight sender)
BCAST      = b"\xff\xff\xff\xff\xff\xff"

DETECT_ETYPE = b"\x07\x00"   # 0x0700 detection query
RESP_TYPE_HI = 0x08          # 0x08xx -> card reply (0x0805)


def mac(b):
    return ":".join("%02x" % x for x in b)


def carrier_up(iface):
    try:
        with open("/sys/class/net/%s/carrier" % iface) as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def build_detection(receiver_id=0):
    # 271-byte frame: 14B eth header + 257B payload, type 0x0700.
    frame = bytearray(271)
    frame[0:6]   = CARD_MAC        # dst = card
    frame[6:12]  = SENDER_MAC      # src = us
    frame[12:14] = DETECT_ETYPE    # ethertype 0x0700
    frame[16]    = receiver_id & 0xff
    return bytes(frame)


def decode_response(buf):
    """Best-effort decode of a 0x0805 reply (FPP offsets, after 14B header)."""
    d = buf[14:]
    out = {}
    if len(d) >= 4:
        out["firmware"] = "%d.%d" % (d[2], d[3])
    if len(d) >= 25:
        w = struct.unpack(">H", d[21:23])[0]
        h = struct.unpack(">H", d[23:25])[0]
        out["cabinet_wxh"] = "%dx%d" % (w, h)
    if len(d) >= 42:
        out["rx_packet_count"] = struct.unpack(">I", d[38:42])[0]
    if len(d) >= 50:
        out["uptime_ms"] = struct.unpack(">I", d[46:50])[0]
    if len(d) >= 86:
        out["receiver_id"] = d[85]
    return out


def main():
    print("Interface : %s" % IFACE)
    if not carrier_up(IFACE):
        print("LINK DOWN  : no carrier on %s." % IFACE)
        print("            Power the panel + 5A-75E and connect Cat5/6 from this")
        print("            Mac mini to the card's INPUT RJ45, then re-run.")
        # Keep going anyway in case carrier flaps; the sniff loop is harmless.
    else:
        print("LINK UP    : carrier present.")

    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    except PermissionError:
        sys.exit("Need root: run with  sudo python3 %s %s" % (sys.argv[0], IFACE))
    s.bind((IFACE, 0))
    s.settimeout(1.0)

    detect = build_detection()
    seen_macs = {}
    card = None
    deadline = time.time() + 8.0
    next_probe = 0.0
    print("\nProbing for up to 8s (sending 0x0700, listening for 0x0805)...\n")

    while time.time() < deadline and card is None:
        now = time.time()
        if now >= next_probe:
            try:
                s.send(detect)
                # also try a broadcast-dst variant in case this fw wants it
                s.send(BCAST + detect[6:])
            except OSError as e:
                print("send failed (%s) - link probably still down" % e)
            next_probe = now + 1.0

        try:
            buf = s.recv(2048)
        except socket.timeout:
            continue
        if len(buf) < 14:
            continue

        dst, src, etype = buf[0:6], buf[6:12], buf[12:14]
        # ignore frames we just sent (our own src MAC)
        if src == SENDER_MAC:
            continue
        key = mac(src)
        if key not in seen_macs:
            seen_macs[key] = (etype.hex(), len(buf))
            print("  frame from %s  ethertype 0x%s  len %d" % (key, etype.hex(), len(buf)))

        if etype[0] == RESP_TYPE_HI:   # 0x08xx -> Colorlight reply
            card = (src, buf)
            break

    print()
    if card:
        src, buf = card
        info = decode_response(buf)
        print("=" * 56)
        print("  CARD FOUND — Colorlight receiver replied (0x0805)")
        print("  MAC        : %s" % mac(src))
        for k, v in info.items():
            print("  %-11s: %s" % (k, v))
        print("=" * 56)
        print("\n  raw reply (first 96 bytes):")
        hexb = buf[:96].hex()
        for i in range(0, len(hexb), 32):
            print("   ", hexb[i:i + 32])
    elif seen_macs:
        print("No 0x0805 handshake reply, but these non-local stations were seen:")
        for m, (et, ln) in seen_macs.items():
            print("  %s  ethertype 0x%s  len %d" % (m, et, ln))
        print("(One of these is likely the card — share this output.)")
    else:
        print("No frames seen. Either the link is down, the card is unpowered,")
        print("or it stays silent until queried differently. Confirm link first:")
        print("  cat /sys/class/net/%s/carrier   # want 1" % IFACE)

    s.close()


if __name__ == "__main__":
    main()
