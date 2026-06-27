# Sender-wall recommendation — after the Session-6 dynamic probe

*Written 2026-06-26 (Session 6). Settles the DYNAMIC-PROBE-BRIEF question with a
LIVE result, then ranks the remaining options. Read alongside the project memory
and `HANDOFF.md`.*

## The experiment we ran (DYNAMIC-PROBE-BRIEF)

Built `re/wine/probe.c` → `probe.exe` (extends `cap2.c`: keeps the inline
`Nic_Write`/`Nic_Read` hooks routing through our wpcap handle on enx). It calls
the device-manager **refresh `vtbl[0x10]` directly** to see whether that populates
the device list with raw-L2 I/O our card can answer. Run wrapper:
`re/wine/run_probe.sh` (tcpdump on enx + `wine probe.exe`).

### Result (read-only run, panel idle — no config written)

```
mgr=...44520                                  # GetHwDeviceManager() OK (=0x180374520)
vt[2] (refresh) = ...24f70  rva=0x154f70      # EXACTLY fcn.180154f70 as predicted
refresh(mgr, 0) = 0xe0830101  Nic_Write+=0 Nic_Read+=0  GetCount=0
refresh(mgr, 1) = 0xe0830101  Nic_Write+=0 Nic_Read+=0  GetCount=0
DetectAll (after refresh) = 0xe0830240  GetCount=0
probe_*.pcap frame_count = 0 ; nicwrite_frames.txt = 0 bytes
```

**Answers to the brief's one question, with evidence:**
- **Did the refresh emit raw-L2 frames?** NO. Zero `Nic_Write`, zero `Nic_Read`,
  zero frames on the wire (empty pcap + empty `nicwrite_frames.txt`).
- **Did a device register?** NO. `GetCount` stayed 0; `DetectAll` still
  `0xe0830240`. Error codes did not improve.

### Why (static corroboration, bounded — not a new RE rabbit hole)

- The refresh's readiness gate `fcn.18015e5e0` **PASSED** this time: the
  gate-fail branch returns `0xe083123b` (`0x180154fd5`), and we did NOT get that.
  So execution entered the detection block at `0x180154fdf`.
- That detection block is **winsock/IP-based, not raw-L2.** CLTDevice imports
  `ws2_32` (ordinals incl. 23=WSAStartup, 8/9/16=socket/recv family); the refresh
  detection chain (`0x18015e410` build-device → `0x18014f2c0` → `0x180153790` →
  `0x18015e750/ec80/f090` …) runs the WSAStartup-bracketed scan and returns
  `0xe0830101` (propagated from a socket callee). CLTDevice statically imports
  ONLY `Nic_Write`+`Nic_Read` from CLTNic, and **neither fired** — proving the
  refresh's detection does not use the raw-L2 path at all.

**Decision Rule branch hit = #3:** *"Refresh does NO raw-L2 I/O (socket/IP only)
and no device registers → the x64 LEDSetting DLL is the WRONG abstraction for our
PC→raw-L2-receiver topology. STOP pursuing it."*

## What this means (the root cause, now firmly established across 6 sessions)

The entire Colorlight DLL stack assumes a **sender-card topology**: PC →
*sender card* (which has an IP, talked to over winsock) → *receiver card* (raw
L2). Our topology is **PC NIC → receiver directly, raw L2** (proven: the card
answers `detect_5a75e.py`/`pcaptest2.exe` `0x0700`→`0x0805`, fw 6.0). Every DLL
path therefore hits a "no sender registered" wall:
- export `DetectAll` → mgr `vtbl+0x128` (current-sender) = NULL → `0xe0830240`
  (never reaches `Nic_Write`);
- manager refresh `vtbl+0x10` → passes the gate but runs a **winsock** scan our
  raw-L2 card can't answer → `0xe0830101`, registers nothing, no `Nic_Write`.

There is no clean DLL entry point that does "configure a raw-L2 receiver directly
from a PC NIC" because Colorlight's product never does that — there is always a
sender. Forcing it would mean fabricating sender/screen state the GUI itself
won't create offline (open-ended; SENDER-WALL-BRIEF options A–E). **Not worth it.**

## Ranked options going forward

**1. (RECOMMENDED) Option F — finish the config wire-format RE directly; replay
from pure Python.** No purchase, uses assets we already have, Linux-native
forever. We hold: `re/data_emu.txt` (the receiver FPGA's OWN auto-generated input
sim = authoritative DISPLAY wire format, cmd bytes 0x05/0x18/0x03/0x02/0x55/0xFF),
`re/emu/records.json` (CLTDevice's 270 computed SAVE-protocol payloads), and
working raw L2 send/recv. The single remaining gap is the **record→wire reframe**
(+ section order + checksum). Concrete next 3 steps:
  - (a) Decode `data_emu.txt` fully into per-section wire templates (we have the
    layout; fill placeholders from the records' 256B payload chunks by section
    code: 0x07 basic/route/LUT, 0x09 gamma/calib, 0xe9 …).
  - (b) Cross-check against `re/capture/config_send.pcap` (we already captured a
    config send attempt) and the known-good `0x0700`/`0x0805` framing.
  - (c) Send section-by-section to the live card with the panel watched; the card
    has no "sender" concept — it just needs the right bytes. Iterate on the
    `0x0805` reply's config fields flipping non-zero.

**2. (ROBUST FALLBACK) Plan B — flash the open gateware**
(`colorlight_5a-75e_artnet/top.bit`, panel_type=0 = our 64×64 1/32, DP5125D +
SM5166PS confirmed standard). Makes the board a fully Linux-native Art-Net HUB75
controller — no LEDVISION ever, most robust long-term. **Blocker: needs a ~$5
DirtyJTAG programmer** (RP2040/Pico or Blue Pill or FT232) we don't have. If
Option F stalls, buy one. (Over-ethernet flash via `TransparentSendLoadRcvFpga`
is brick-risky — avoid.)

**3. (DROP) DLL-driven paths (A2a GUI, A2b cold harness, x64 refresh, SENDER-WALL
options A–E).** All blocked by the same sender-topology mismatch, now confirmed
dynamically for the x64 refresh. Stop spending effort here.

## Honest uncertainty

- Option F's reframe is the same gap that has resisted blind-tuning before; the
  win is that `data_emu.txt` + `records.json` give the actual bytes, so it's
  decode-and-fill, not guess. Still real RE effort — estimate a focused session.
- We have NOT re-tested the **32-bit LEDVISION** refresh for raw-L2 (Session 3
  found its sender vector is persisted-state-backed too). Given the x64 result and
  the shared topology assumption, low odds it differs — not worth a probe before
  trying Option F.

## Artifacts from this session
- `re/wine/probe.c`, `probe.exe`, `re/wine/run_probe.sh` — the dynamic probe.
- `re/wine/probe_*.log` — full run output. `re/capture/probe_*.pcap` — empty (0
  frames, as expected). `re/capture/nicwrite_frames.txt` — empty.
