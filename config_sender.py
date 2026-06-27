#!/usr/bin/env python3
"""
config_sender.py - push a Colorlight 5A-75E receiver configuration to the card
from Linux over raw L2 Ethernet, reproducing what LEDVISION's
"Save parameters to receiver" does.

WHY THIS EXISTS
  A brand-new 5A-75E drives nothing until it holds a valid receiver config.
  LEDVISION (Windows-only) normally writes it. We reverse-engineered the wire
  format instead. See README.md "Reverse-engineering effort".

WHAT WE KNOW (sources: re/data_emu.txt = Colorlight's own auto-generated
receiver-input sim, + static RE of CLTDevice.dll):

  A config is sent as a SET OF L2 FRAMES, one (or more, split by subframe)
  per config "section". The on-wire frame layout (from data_emu.txt, which is
  authoritative - it is the byte stream the receiver FPGA expects):

      offset  field
      0..5    dst MAC = 11:22:33:44:55:66   (the card)
      6..11   src MAC = 22:22:33:44:55:66   (us; card appears to ignore it)
      12      COMMAND byte   (which section this frame carries)
      13..14  serial number (u16, big-endian)   -- 0 for config writes
      15      subframe number (u8)              -- 0,1,.. for multi-frame sections
      16..    section payload bytes (verbatim from the .rcvp section)

  COMMAND bytes (decoded from data_emu.txt + the DLL's VHDL-export strings):
      0x05  basic parameters        (#-BASICPARAM-#)
      0x18  scan schedule / table   (#-SCANSCHEDULE-#)
      0x03  routing table           (#-BASICROUTE-#)
      0x02  card / control area     (#-CARDAREA-#, "10 bytes per card")
      0x10  snapshot / void table   (#-VOID_TABLE-#)
      0x01  switch frame            (#-SWITCH_FRAME_PARAM-#)
      0xFF  init / first frame
      0x55  display data (pixels)   -- handled by colorlight_stock_test.py

  After each frame the card returns an ack (the DLL's sendCmd does a Nic_Read
  and checks status bytes 0x7b/0x7d/0x84 = ok-ish, 0x7e = fail). So we send
  each frame and LISTEN for the card's reply as feedback.

.rcvp CONTAINER (parsed below; verified against several files):
      0x00..0x0F  16-byte fixed magic (8b2da643 e9cbe243 9bb4e7a3 b3e6c30d)
      0x10..0x17  format header: u32=4, then 00 01 07 01 (version 0x0107)
      0x18..0x113 fixed BASIC-PARAM block (260B incl header). 0x18=width,
                  0x19=scan, RGB order ~0x43-45, clock/brightness floats ~0xc2+
      0x114..     length-prefixed sections, descriptor = [u16 len_LE][0x07][idx]
                  (len includes the 4-byte descriptor). idx seen: 0x02, 0x03.
      last 4 B    file checksum (NOT standard CRC32; only needed to re-serialize
                  a .rcvp, which we don't do - we send the stock file as-is)

UNCERTAIN (to resolve empirically against the live card / next RE pass):
  - exact mapping of descriptor idx -> command byte. Hypothesis here:
    idx 0x02 -> cmd 0x02 (cardarea), idx 0x03 -> cmd 0x03 (routing).
    The big idx-0x03 LUT (2048 x 3B identity) might instead be the scan
    table (cmd 0x18). Both are selectable below; test on the card.
  - whether large sections are chunked by raw bytes or are transformed
    (compacted) before sending. We chunk by bytes (<=1400) as a first attempt.
  - whether the basic-param payload is the block from 0x10 or 0x18.

USAGE
  sudo python3 config_sender.py <iface> <rcvp-file> [--only 05,02,03] [--dry]
  e.g.
  sudo python3 config_sender.py enx9c69d388d76e \
      "re/config_files/General Parameters(Fullcolor)/26- full-color thirty-two scan.rcvp"
"""
import socket
import struct
import sys
import time

DST = b"\x11\x22\x33\x44\x55\x66"   # card
SRC = b"\x22\x22\x33\x44\x55\x66"   # us (Colorlight sender MAC)

ETH_P_ALL = 0x0003
MAX_PAYLOAD = 1400                  # bytes per frame before we split into subframes


# ---------------------------------------------------------------- .rcvp parsing
MAGIC = bytes.fromhex("8b2da643e9cbe2439bb4e7a3b3e6c30d")


def parse_rcvp(data):
    """Return dict with magic ok, basic-param block, and list of sections
    [{idx, tag, off, payload}]. Tolerant: logs what it finds."""
    out = {"magic_ok": data[:16] == MAGIC, "size": len(data)}
    # fixed basic-param block: 0x10 .. 0x114  (header 0x10-0x17 + params)
    out["basic_block"] = data[0x10:0x114]      # full 260B block (incl 8B header)
    out["basic_params"] = data[0x18:0x114]     # params only (after 8B header)
    out["width"] = data[0x18]
    out["scan"] = data[0x19]

    sections = []
    off = 0x114
    end = len(data) - 4                         # last 4B = file checksum
    while off + 4 <= end:
        length = struct.unpack_from("<H", data, off)[0]
        tag = data[off + 2]
        idx = data[off + 3]
        if length < 4 or off + length > end + 0:
            break
        payload = data[off + 4: off + length]
        sections.append({"idx": idx, "tag": tag, "off": off,
                         "length": length, "payload": payload})
        off += length
    out["sections"] = sections
    out["trailer"] = data[-4:]
    return out


# ----------------------------------------------------------------- frame build
def build_frames(cmd, payload, max_payload=MAX_PAYLOAD, serial=0):
    """One section -> list of L2 frames, split into subframes if large.
    Frame = dst|src|cmd|serial(2,BE)|subframe(1)|payload[, padded to 60]."""
    frames = []
    if len(payload) <= max_payload:
        chunks = [payload]
    else:
        chunks = [payload[i:i + max_payload]
                  for i in range(0, len(payload), max_payload)]
    for sub, chunk in enumerate(chunks):
        hdr = bytes([cmd, (serial >> 8) & 0xff, serial & 0xff, sub])
        frame = DST + SRC + hdr + chunk
        if len(frame) < 60:
            frame += b"\x00" * (60 - len(frame))
        frames.append(frame)
    return frames


# --------------------------------------------------------------------- sending
def open_socket(iface):
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    s.bind((iface, 0))
    s.settimeout(0.4)
    return s


def send_and_listen(s, frames, label):
    """Send each frame, drain any card replies (non-self frames) briefly."""
    replies = []
    for i, fr in enumerate(frames):
        s.send(fr)
        # listen ~0.2s for a reply from the card
        t = time.time()
        while time.time() - t < 0.2:
            try:
                buf = s.recv(2048)
            except socket.timeout:
                break
            if buf[6:12] == SRC:            # ignore our own frames
                continue
            replies.append(buf)
    tag = " <- %d reply(ies)" % len(replies) if replies else ""
    print("  sent %-22s %d frame(s), %d B payload%s"
          % (label, len(frames), sum(len(f) - 16 for f in frames), tag))
    for r in replies[:2]:
        print("      reply src=%s cmd=0x%02x len=%d  %s"
              % (":".join("%02x" % b for b in r[6:12]), r[12], len(r),
                 r[12:28].hex()))
    return replies


# ------------------------------------------------------------------------ main
# descriptor idx -> wire command byte (HYPOTHESIS - tweak & test on card)
IDX_TO_CMD = {0x02: 0x02, 0x03: 0x03}

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    iface = sys.argv[1]
    path = sys.argv[2]
    only = None
    dry = "--dry" in sys.argv
    if "--only" in sys.argv:
        only = set(int(x, 16) for x in sys.argv[sys.argv.index("--only") + 1].split(","))

    data = open(path, "rb").read()
    p = parse_rcvp(data)
    print("=" * 64)
    print("rcvp: %s" % path)
    print("  size=%d  magic_ok=%s  width=%d scan=%d"
          % (p["size"], p["magic_ok"], p["width"], p["scan"]))
    for sec in p["sections"]:
        print("  section idx=0x%02x tag=0x%02x off=0x%x len=%d payload=%dB -> cmd 0x%02x"
              % (sec["idx"], sec["tag"], sec["off"], sec["length"],
                 len(sec["payload"]), IDX_TO_CMD.get(sec["idx"], sec["idx"])))
    print("=" * 64)

    # Build the send plan: (cmd, payload, label)
    plan = []
    plan.append((0x05, p["basic_params"], "basic-param(0x05)"))
    for sec in p["sections"]:
        cmd = IDX_TO_CMD.get(sec["idx"], sec["idx"])
        plan.append((cmd, sec["payload"], "section idx%02x(0x%02x)" % (sec["idx"], cmd)))

    if only is not None:
        plan = [x for x in plan if x[0] in only]
        print("filtering to commands: %s" % sorted(only))

    if dry:
        for cmd, payload, label in plan:
            frames = build_frames(cmd, payload)
            print("  [dry] %-22s cmd=0x%02x %d frame(s) %dB"
                  % (label, cmd, len(frames), len(payload)))
        return

    s = open_socket(iface)
    print("Sending config on %s ...\n" % iface)
    for cmd, payload, label in plan:
        frames = build_frames(cmd, payload)
        send_and_listen(s, frames, label)
        time.sleep(0.05)
    print("\nDone. Now run colorlight_stock_test.py and watch the panel.")
    s.close()


if __name__ == "__main__":
    main()
