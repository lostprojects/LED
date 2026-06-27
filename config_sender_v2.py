#!/usr/bin/env python3
"""
config_sender_v2.py - push a Colorlight 5A-75E receiver configuration using the
DLL's OWN serialized output, extracted by emulating CLTDevice.dll.

WHY THIS IS DIFFERENT FROM config_sender.py
  v1 guessed the per-section payloads by slicing the raw .rcvp bytes. That was
  wrong: the card wants the DLL's *reformatted* payload. We now run the DLL's
  real serializer offline (re/emu/harness.py, a Unicorn emulation) over the
  .rcvp and capture the exact "frame records" that CLTReceiverGetSaveCMDData
  produces - i.e. the byte-exact data LEDVISION's "Save parameters to receiver"
  transmits. Those records are in re/emu/records.json.

WIRE FRAMING (established by static RE of CLTDevice.dll + CLTNic.dll):
  CLTDevice builds each record BODY:
      byte0      0x06 / 0x26     frame class/marker
      byte1..2   00 00           (serial)
      byte3      0x26
      byte4      00
      byte5      0x23 (section header) / 0x85 (data block)
      byte6      00
      byte7      section code     (0x07 / 0x09 / 0xe9 ...)
      byte8      block index      (0,1,2,...)
      byte9      00
      byte10..   up to 256 bytes of payload
  The MAC header is NOT in CLTDevice (the literal 11:22:33:44:55:66 appears
  nowhere in it) - CLTNic prepends it. So the on-wire Ethernet frame is:
      [dst MAC 11:22:33:44:55:66][src MAC 22:22:33:44:55:66] + record_body
  We send that raw via AF_PACKET (the NIC adds the preamble + FCS).

  After each block the card replies; the DLL's Nic_Read treats status bytes
  0x7b/0x7d/0x84 as ok and 0x7e as fail. We send a block, wait for the reply,
  and report it.

USAGE
  sudo python3 config_sender_v2.py <iface> [records.json] [--no-wait] [--dry]
  e.g. sudo python3 config_sender_v2.py enx9c69d388d76e
"""
import socket, struct, sys, time, json, os

DST = b"\x11\x22\x33\x44\x55\x66"     # card
SRC = b"\x22\x22\x33\x44\x55\x66"     # us
ETH_P_ALL = 0x0003

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RECS = os.path.join(HERE, "re", "emu", "records.json")


def load_records(path):
    recs = json.load(open(path))
    out = []
    for r in recs:
        body = bytes.fromhex(r["body"])[: r["len"]]   # 266 bytes typically
        out.append({"k": r["k"], "code": r["code"], "len": r["len"], "body": body})
    return out


def open_sock(iface):
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    s.bind((iface, 0)); s.settimeout(0.4)
    return s


def detect(s, timeout=1.5):
    """Send 0x0700 detection, return the card's 0x0805 reply (or None)."""
    fr = bytearray(271); fr[0:6] = DST; fr[6:12] = SRC; fr[12:14] = b"\x07\x00"
    t = time.time()
    while time.time() - t < timeout:
        s.send(bytes(fr))
        try:
            while True:
                buf = s.recv(2048)
                if buf[6:12] == DST and buf[12:14] == b"\x08\x05":
                    return buf
        except socket.timeout:
            pass
    return None


def send_block(s, body, wait=True):
    """Send one record body as [dst][src]+body; collect any card reply."""
    frame = DST + SRC + body
    if len(frame) < 60:
        frame += b"\x00" * (60 - len(frame))
    s.send(frame)
    replies = []
    if wait:
        t = time.time()
        while time.time() - t < 0.15:
            try:
                buf = s.recv(2048)
            except socket.timeout:
                break
            if buf[6:12] == SRC:
                continue
            replies.append(buf)
    return replies


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    iface = sys.argv[1]
    recpath = DEFAULT_RECS
    for a in sys.argv[2:]:
        if a.endswith(".json"):
            recpath = a
    wait = "--no-wait" not in sys.argv
    dry = "--dry" in sys.argv

    recs = load_records(recpath)
    codes = {}
    for r in recs:
        codes.setdefault(r["code"], 0)
        codes[r["code"]] += 1
    print("Loaded %d records from %s" % (len(recs), recpath))
    print("  section codes: %s" % {hex(k): v for k, v in codes.items()})
    print("  frame sizes: body %d B -> wire %d B (incl 12B MAC)"
          % (recs[0]["len"], recs[0]["len"] + 12))

    if dry:
        for r in recs[:6]:
            print("  [dry] rec[%d] code=0x%x %dB body=%s"
                  % (r["k"], r["code"], r["len"], r["body"][:16].hex()))
        return

    s = open_sock(iface)
    before = detect(s)
    if before is None:
        print("WARNING: no 0x0805 reply - card not responding to detection")
    else:
        print("card alive; 0x0805 reply %dB" % len(before))

    print("\nSending %d config blocks ...\n" % len(recs))
    ack_ok = ack_fail = ack_other = 0
    t0 = time.time()
    for r in recs:
        reps = send_block(s, r["body"], wait=wait)
        for rep in reps:
            st = rep[12] if len(rep) > 12 else None
            if st in (0x7b, 0x7d, 0x84): ack_ok += 1
            elif st == 0x7e: ack_fail += 1
            else: ack_other += 1
        if r["k"] < 3 or r["body"][5] == 0x23:   # show headers + first few
            tag = "HDR" if r["body"][5] == 0x23 else "dat"
            rb = reps[0][12:16].hex() if reps else "-"
            print("  rec[%3d] %s code=0x%02x idx=%3d -> %d reply (op %s)"
                  % (r["k"], tag, r["code"], r["body"][8], len(reps), rb))
    dt = time.time() - t0
    print("\nSent %d blocks in %.2fs. acks: ok=%d fail=%d other=%d"
          % (len(recs), dt, ack_ok, ack_fail, ack_other))

    after = detect(s)
    if before and after:
        diff = [i for i in range(min(len(before), len(after))) if before[i] != after[i]]
        print("0x0805 reply: %d bytes changed after config" % len(diff))
        if diff:
            print("  changed offsets:", [hex(x) for x in diff[:40]])
    s.close()
    print("\nWatch the panel. If still garbage, the blocks may need a different")
    print("framing/order or an apply/switch frame - iterate against the card.")


if __name__ == "__main__":
    main()
