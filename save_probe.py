#!/usr/bin/env python3
"""
save_probe.py - empirically probe the Colorlight 5A-75E SAVE/flash wire framing.

We have the DLL's complete serialized config (re/emu/records.json, 542 records,
each = 10B internal header [26 00 00 26 00 (23|85) 00 SEC IDX 00] + <=256B payload).
The on-wire frame (after the 12B MAC header CLTNic prepends) is unknown; sending
the raw record body (byte12 = 0x26) got no acks. This script tries several framing
hypotheses on a few representative records and listens for ANY card reply that is
NOT the periodic 0x0805 status broadcast (or an 0x0805 whose body changed),
printing the ethertype + first bytes so we can spot an ack.

USAGE: sudo python3 save_probe.py enx9c69d388d76e
"""
import socket, struct, sys, time, json, os

DST = b"\x11\x22\x33\x44\x55\x66"     # card
SRC = b"\x22\x22\x33\x44\x55\x66"     # us
HERE = os.path.dirname(os.path.abspath(__file__))

def open_sock(iface):
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    s.bind((iface, 0)); s.settimeout(0.25)
    return s

def listen(s, secs=0.35):
    """Collect frames not sent by us; return list of (ethertype, raw)."""
    out=[]; t=time.time()
    while time.time()-t < secs:
        try: buf=s.recv(2048)
        except socket.timeout: break
        if buf[6:12]==SRC: continue          # ignore our own echo
        et=buf[12:14].hex()
        out.append((et, buf))
    return out

def pad(fr):
    return fr + b"\x00"*(60-len(fr)) if len(fr)<60 else fr

def send_listen(s, frame, label):
    s.send(pad(frame))
    reps=listen(s)
    tags={}
    for et,b in reps:
        tags.setdefault(et,0); tags[et]+=1
    note=""
    # an interesting reply = anything other than the lone periodic 0x0805
    interesting=[ (et,b) for et,b in reps if et!="0805" ]
    print("  %-44s -> replies %s%s" % (label, tags or "none",
          "   <<< NON-0805!" if interesting else ""))
    for et,b in interesting[:2]:
        print("        et=%s len=%d : %s" % (et, len(b), b[:32].hex()))
    return reps

def main():
    iface=sys.argv[1]
    recs=json.load(open(os.path.join(HERE,"re","emu","records.json")))
    def body(k):
        r=recs[k]; return bytes.fromhex(r["body"])[:r["len"]]
    s=open_sock(iface)

    # baseline: how often does the card emit 0x0805 unprompted?
    print("baseline (no send), 0.5s listen:")
    base=listen(s,0.5); print("  spontaneous frames:", {})
    print()

    # representative records: header(0), first data of a couple sections
    targets = []
    for k,r in enumerate(recs):
        b=bytes.fromhex(r["body"])
        if k==0 or (b[5]==0x85 and b[8]==0):  # header + idx0 of each section
            targets.append(k)
    targets=targets[:6]
    print("probing records:", targets)

    for k in targets:
        bd=body(k)
        sec=bd[7]; idx=bd[8]; payload=bd[10:]
        print("\nrecord[%d] sec=0x%02x idx=%d paylen=%d head=%s"
              % (k, sec, idx, len(payload), bd[:12].hex()))
        # framing hypotheses (wire body that follows the 12B MAC header)
        H = {
          "F1 raw body (et 0x2600)"      : bd,
          "F2 body b0=0x06 (et 0x0600)"  : b"\x06"+bd[1:],
          "F3 wrap 07 00 + body"         : b"\x07\x00"+bd,
          "F4 et 0x0107 + body"          : b"\x01\x07"+bd,
          "F5 cmd=sec: [sec 00 00 idx]+payload" : bytes([sec,0,0,idx])+payload,
          "F6 et0x0107 [00 idx]+payload" : b"\x01\x07\x00"+bytes([idx])+payload,
        }
        for label,wirebody in H.items():
            send_listen(s, DST+SRC+wirebody, label)
            time.sleep(0.05)

    s.close()
    print("\nDone. Watch the panel. Any '<<< NON-0805' line = candidate ack.")

if __name__=="__main__":
    main()
