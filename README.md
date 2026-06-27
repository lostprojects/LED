# LED Bar Menu

Driving **12× 64×64 RGB LED panels** from a **Linux Mac mini** through a
**Colorlight 5A-75E** receiving card, to build a digital menu board for a bar.

> **Status (2026-06-25) — STRATEGY PIVOT. The plan of record is now
> [`LED-PLAN.md`](LED-PLAN.md); read that first.** Network link + comms work;
> `.rcvp` mapped; `data_emu.txt` decoded; a Unicorn harness can run the DLL's
> config serializer offline (`re/emu/records.json`). But that path stalled on the
> hardest possible step — reversing the record→wire reframing inside CLTNic's
> threaded/throwing send path. **We are abandoning that rabbit hole.**
>
> The blocker existed only because of one wrong assumption ("Wine can't do raw
> Ethernet"). **Wine ≥1.7.25 forwards `wpcap.dll` → real Linux `libpcap`, and
> `CLTNic.dll` is a WinPcap layer.** So we run the **real LEDVISION on this Linux
> box under Wine**, point it at the USB NIC, let it configure the **real card**,
> and `tcpdump` the exact config frames — no Windows, no JTAG, no DLL emulation.
> **VERIFIED VIABLE 2026-06-25:** CLTNic confirmed userland WinPcap; Wine 9.0 +
> 32-bit `wpcap.so`→`libpcap.so.0.8` bridge installed and resolving. See
> [`LED-PLAN.md`](LED-PLAN.md) §0b.
>
> **Session-3 update (2026-06-25):** Wine runs the real DLLs on both prefixes —
> they load, all config exports resolve, the NIC enumerates (`enx9c69d388d76e` =
> adapter index 1). But a **cold code-only harness can't push the config**: the
> 32-bit config exports return `0xe0830040` because the library's internal NIC
> "sender" must be registered first, and that registration is backed by
> **GUI-persisted screen/sender state**. **So the next step is A2a: run the real
> 32-bit `LEDVISION.exe` GUI under Wine, set up the NIC sender, push the `.rcvp`,
> and `tcpdump` the frames.** (Earlier "GUI is a dead end" applied only to the x64
> LEDSetting tool; the 32-bit LEDVISION GUI is untested and is the path.)
> **⚠️ Run that GUI on `Xvfb :99`, NEVER `:0` as root** — LEDVISION's embedded
> Chromium/CEF on the user's `:0` crashed the desktop + VSCode before (see project
> memory). Details: `HANDOFF.md` §"SESSION 3", `LED-PLAN.md` §0b update, memory.
>
> **Wire format (decoded, for reference):** a config = one L2 frame per section:
> `dst 11:22:33:44:55:66 | src 22:22:33:44:55:66 | byte12=CMD | serial(u16) |
> subframe | payload`. CMDs: `0x05` basic params, `0x18` scan, `0x03` route,
> `0x02` card area, `0x10` void, `0x01` switch, `0xFF` init, `0x55` display.
> (The Wine capture will give the byte-exact frames directly, superseding guesswork.)

---

## Table of contents
- [Hardware](#hardware)
- [Architecture / data path](#architecture--data-path)
- [Networking — important](#networking--important)
- [What works today](#what-works-today)
- [Approaches considered](#approaches-considered)
- [Reverse-engineering effort](#reverse-engineering-effort)
- [Work remaining](#work-remaining)
- [File inventory](#file-inventory)
- [How to run](#how-to-run)
- [Key facts & gotchas](#key-facts--gotchas)

---

## Hardware

| Item | Detail |
|---|---|
| Host | **Macmini8,1** (2018, Intel, Apple **T2** chip), Linux Mint 22.3 (kernel 6.14) |
| Controller | **Colorlight 5A-75E** receiving card (Lattice ECP5 LFE5U-25F, W25Q32 flash), firmware **6.0** |
| Panels | **12× 64×64** HUB75, **1/32 scan**. Drivers: **DP5125D** (column/data) + **SM5166PS** (row/scan, 138-decoder type) — both standard |
| Panel NIC | **USB ASIX AX88179B** gigabit adapter → iface **`enx9c69d388d76e`** |
| Internet | USB WiFi dongle (Realtek RTL88x2bu) — **do not disturb; it's our only uplink** |

Currently **one** panel is connected for bring-up; scale to 12 afterwards.

---

## Architecture / data path

```
Linux (enx9c69d388d76e, raw L2 Ethernet)
        │  Colorlight protocol (no IP)
        ▼
  Colorlight 5A-75E  ──HUB75 ribbon──►  64×64 panel(s)
```

The 5A-75E is a *receiver* card. We drive it directly from the Mac mini's USB
Ethernet adapter using raw Layer-2 frames (no sending card, no IP). The card must
hold a valid **receiver configuration** before it will drive the HUB75 outputs —
that config is the missing piece (see below).

---

## Networking — important

- **The Mac mini's built-in Ethernet (`enp4s0`, Broadcom BCM57766/`tg3`) is DEAD
  under Linux** and cannot be used. It never links (carrier 0) against the card,
  a fresh cable, or a switch; the PHY shows no reaction to a cable. Root cause:
  on the T2 Mac the NIC's NVRAM/firmware never initializes
  (`tg3: No firmware running`, `Cannot get nvram lock`). Tried and failed: driver
  reload, forced speed/duplex, EEE off, `pcie_aspm=off pm_async=off`, PCIe reset,
  PCIe remove+rescan. There is no `tg3` patch for this. **Abandoned.**
- **Use the USB adapter** → `enx9c69d388d76e`. It links at gigabit.
- The USB adapter must go in a **USB-C / Thunderbolt** port (USB-A is blocked by
  the WiFi dongle; the dongle is the internet uplink and must not be moved). It
  also must be plugged **directly**, not through the USB-C video dock/hub (it
  didn't enumerate behind the hub).
- All scripts target `enx9c69d388d76e`, **not** `enp4s0`.

---

## What works today

- ✅ **Gigabit link** from Mac mini → 5A-75E via the USB adapter.
- ✅ **Two-way comms** with the card over the stock Colorlight protocol:
  `detect_5a75e.py` sends a `0x0700` detection frame and the card replies with
  `0x0805` (firmware 6.0, card MAC `11:22:33:44:55:66`).
- ✅ Pixel-frame sender written (`colorlight_stock_test.py`) — frames are accepted
  by the card.
- ❌ **Panel does not display.** A brand-new 5A-75E with no receiver config drives
  nothing; the panel shows only its idle power-on state ("red lines"). This is
  expected and is exactly the problem we're solving.

---

## Approaches considered

| Path | Verdict |
|---|---|
| **A. Stock firmware + configure with LEDVISION (native Windows)** | LEDVISION is Windows-only; no Windows machine available. Out as-is. |
| **B. Flash open Art-Net gateware via JTAG** | Clean end-state, but needs a JTAG programmer (Pico/Blue Pill/FTDI). **Fallback** — check for a spare board first. |
| **C. Static RE of LEDVISION DLLs → reproduce config from Linux** | Tried hard (Unicorn harness, `records.json`). Stalled on the record→wire reframe. **Abandoned as primary** — too deep/brittle. |
| **D. Run real LEDVISION under Wine, bridge `wpcap`→`libpcap` to the real NIC, capture config frames** | **← CHOSEN (Plan A).** No Windows, no JTAG, no purchase. **Verified viable 2026-06-25.** Gives byte-exact config frames by observation. See [`LED-PLAN.md`](LED-PLAN.md). |

Why D beats C: C dismissed Wine on the false belief it can't do raw Ethernet —
in fact Wine forwards WinPcap to host libpcap, and CLTNic is a WinPcap layer. D
turns a multi-session binary-RE problem into a one-time `tcpdump` capture.

Path B (open gateware, `colorlight_5a-75e_artnet/` + prebuilt `top.bit`) remains
the fallback and is the fastest clean route *if* a ~$4 JTAG programmer (Pico/Blue
Pill/FT232) ever appears.

---

## Reverse-engineering effort

**Goal:** reproduce, from Linux, the L2 frames LEDVISION sends to write a receiver
configuration — then push the config for our 1/32 64×64 panel so the card drives
the HUB75 outputs. Pixels are already solved.

### What we have (all under `re/`)
- **LEDVISION 9.2** downloaded and unpacked (free installer; the CDN requires a
  `Referer: https://en.colorlightinside.com/` header or it 403s; unpack the NSIS
  exe with `7z x`).
- **DLLs** (`re/dll/`), all 32-bit PE:
  - `CLTNic.dll` — network/WinPcap L2 layer (`Nic_Write`, `Nic_SendScreenPicture`,
    `Nic_SetScreenSize`, `Nic_GetNetAdapterInfo`, …).
  - `CLTDevice.dll` — receiver config logic (C++ class `CReceiverOP`).
  - `CommonClass.dll` — shared helpers.
- **Ready-made config files** (`re/config_files/General Parameters(Fullcolor)/`):
  - **`26- full-color thirty-two scan.rcvp`** ← our 1/32 64×64 panel (6458-byte binary).
  - `25- full-color sixteen scan.rcvp` (1/16), plus many other scan types.
- `re/data_emu.txt` — a VHDL testbench that emulates the receiver's RGMII input
  stream (shows the `0x55…0xD5` Ethernet preamble and frame timing) — a useful
  cross-reference for the wire format.

### What we've decoded so far
- **Config schema** — the config is a set of named sections (markers found in the
  binary): `#-BASICPARAM-#`, `#-BASICSCAN-#`, `#-BASICROUTE-#`, `#-SCANSCHEDULE-#`,
  `#-DATA_REMAPPING_TABLE_PARAM-#`, `#-CHIP_REALTIME_PARAM-#`,
  `#-CHIPCUSTOMPLUS_PARAM-#`, `#-GAMATABLE-#`, `#-VOID_ROWCOL_PARAM-#`,
  `#-SWITCH_FRAME_PARAM-#`, `#-CARDAREA-#`, `#-EEPROM_PARAM-#`, …
- **`.rcvp` layout (partial)** — 16-byte header/magic, basic params near offset
  0x10 (contains config ethertype `0x0107`, apparent W/H), an identity
  **data-remapping table** `00 01 … 3f` at 0x70, and a **scan-schedule** table of
  incrementing 16-bit values at 0x130. Maps onto the section schema above.
- **Public API in `CLTDevice.dll`** (the operation we must reproduce):
  - `CLTReceiverRcvParamInitFromFile` — load a `.rcvp`.
  - **`CLTReceiverRcvParamSaveToDevice`** — send/save the config to the card over
    the network *(the target operation)*.
  - `CLTReceiverGetSendCMDData` / `GetSaveCMDData` — return the raw command bytes
    that go on the wire (decompiling these reveals the frame format directly).
  - `CLTReceiverReadbackRcvBasicParam` — read config back (useful to verify).
  - Also present: `TransparentSendLoadRcvFpga`, `SlowUpgradeRcvParam` — the card
    can be **FPGA-reflashed over Ethernet**, a possible JTAG-free route to the
    open gateware as well.
- On-board **chip database** in the DLL (ICN2053/2013/2018, MBI5981/5988, …).

### Tools
- `radare2` 5.5.0 installed (`apt`) for decompiling the 32-bit DLLs.
- Target function addresses (file offset / vaddr in `CLTDevice.dll`):
  - `CLTReceiverRcvParamSaveToDevice` — `0x000e4bb0` / `0x100e57b0`
  - `CLTReceiverGetSaveCMDData` — `0x000e34d0` / `0x100e40d0`
  - `CLTReceiverGetSendCMDData` — `0x000e3480` / `0x100e4080`
  - `CLTReceiverRcvParamInitFromFile` — `0x000e4870` / `0x100e5470`

---

## Work remaining

- [x] **Decode the config wire-frame format.** Done — from `re/data_emu.txt`
  (Colorlight's own auto-generated receiver sim). One L2 frame per section:
  `dst|src|byte12=CMD|serial(u16)|subframe|payload`; CMD bytes 0x05/0x18/0x03/
  0x02/0x10/0x01/0xFF/0x55 (see status note at top). DLL call-path mapped too
  (addresses in project memory).
- [x] **Map the `.rcvp` binary.** Done — magic, fixed basic-param block
  (width@0x18, scan@0x19, RGB order, clock/brightness floats), length-prefixed
  sections `[len][0x07][idx]`, trailing file checksum.
- [x] **Write `config_sender.py` / `bringup_test.py`** and test live. Done —
  the card now **reacts** (pixel frames flicker the panel = HUB75 driven), but
  no clean image yet.
**Plan of record: [`LED-PLAN.md`](LED-PLAN.md).** Remaining work:

- [x] **Verify Plan A (Wine bridge) viability.** Done 2026-06-25 — CLTNic is
  userland WinPcap; Wine 9.0 + 32-bit `wpcap.so`→`libpcap.so.0.8` installed and
  resolving. (See `LED-PLAN.md` §0b.)
- [ ] **NEXT — Wine prefix + config send.** Create the prefix, run LEDVISION (or
  a tiny harness exe calling `CLTReceiverRcvParamInitFromFile` →
  `CLTReceiverRcvParamSaveToDevice`) under Wine, point it at `enx9c69d388d76e`,
  load `26- full-color thirty-two scan.rcvp`, send to the receiver.
- [ ] **Capture ground truth.** `tcpdump -i enx9c69d388d76e -w
  re/capture/config_send.pcap` during the send → byte-exact config frames.
- [ ] **Outcome split:** panel lights → basically done; OR decode the capture and
  static-replay the config from pure Python (`config_sender.py`) → fully
  Linux-native, Wine used once.
- [ ] **Drive content** — render the menu and stream pixels (`bringup_test.py`
  `row_frame` has the corrected `data_emu` pixel layout; lean on
  kostaman/LED_Matrix-1 + FPP for the pixel path).
- [ ] **Scale to 12 panels** — full canvas size + per-panel region mapping.

> Reality check: the Unicorn/static-RE path (abandoned as primary) was the
> deepest, most brittle place to be stuck. Plan A replaces it with an observed
> `tcpdump` capture from the real software running on Linux.

### Superseded (kept as reference, do not resume)
- RE the section serializer `fcn.100cddd0` / the record→wire reframe / driving
  `Nic_Write` under emulation. The Wine capture yields these bytes directly.

### Fallback
If a **JTAG programmer** (Raspberry Pi Pico/Blue Pill/FTDI/CH341A) ever becomes
available, flashing the prebuilt open gateware (`colorlight_5a-75e_artnet/top.bit`,
`openFPGALoader -c dirtyJtag -f --unprotect-flash top.bit`) is a faster, clean
path to an Art-Net controller. See [SETUP.md](SETUP.md).

---

## File inventory

```
LED/
├── LED-PLAN.md                   # ★ PLAN OF RECORD (Plan A = Wine bridge) — read first
├── README.md                     # this file (status + context)
├── HANDOFF.md                    # next-agent quick-start (points at LED-PLAN.md)
├── SETUP.md                      # detailed Path-B (gateware/JTAG) fallback setup notes
├── detect_5a75e.py               # find + handshake the card (works)
├── config_sender.py              # parse .rcvp + send per-section config frames (NEW)
├── bringup_test.py               # config + data_emu-correct pixel test (NEW)
├── colorlight_stock_test.py      # old FPP pixel sender (frame layout is off-by-one;
│                                 #   bringup_test.py has the corrected layout)
├── nic_reset.sh                  # (built-in NIC reset attempts — port is dead)
├── .env                          # SUDO_PASS for privileged cmds — DELETE when done
├── colorlight_5a-75e_artnet/     # open Art-Net gateware (Path B), incl. top.bit
└── re/                           # reverse-engineering assets
    ├── dll/                      #   CLTNic.dll, CLTDevice.dll, CommonClass.dll
    ├── config_files/             #   General Parameters(Fullcolor)/*.rcvp
    ├── data_emu.txt              #   VHDL receiver-stream testbench (frame ref)
    ├── emu/                      #   Unicorn harness + records.json (REFERENCE only — superseded)
    └── capture/                  #   tcpdump captures from the Wine config send (to be created)
```

---

## Setup / dependencies

Python deps are declared in [`pyproject.toml`](pyproject.toml); the full list of
third-party software (proprietary DLLs, vendored gateware, system toolchain) is in
[`THIRD_PARTY.md`](THIRD_PARTY.md).

```bash
# Python packages for the RE harnesses (pefile, unicorn)
pip install -e .            # or: pip install pefile unicorn

# Proprietary Colorlight DLLs are NOT in this repo (git-ignored). To run the
# re/emu/ harnesses, install LEDVISION and copy its DLLs into re/dll/:
#   re/dll/CLTDevice.dll  re/dll/CLTNic.dll  re/dll/CommonClass.dll
# See THIRD_PARTY.md §2.
```

System tools (Wine, radare2, and — for the Plan B gateware — yosys / nextpnr-ecp5 /
openFPGALoader) install via your OS package manager; see `THIRD_PARTY.md` §4.

## How to run

All raw-socket commands need root. `.env` holds `SUDO_PASS`; scripts are invoked
via `sudo`.

```bash
# 1. Confirm the USB NIC + card link
cat /sys/class/net/enx9c69d388d76e/carrier    # want: 1

# 2. Find / handshake the card
sudo python3 detect_5a75e.py enx9c69d388d76e   # expect "CARD FOUND — 0x0805"

# 3. PLAN A — configure the card via the real DLLs under Wine, capturing frames
#    (run the send under sudo so the wpcap→libpcap bridge gets cap_net_raw)
sudo tcpdump -i enx9c69d388d76e -w re/capture/config_send.pcap &   # capture truth
wine LEDVISION.exe   # GUI: select enx9c69d388d76e, load the 1/32 64x64 .rcvp, send to receiver
#   (or a tiny harness exe: InitFromFile(26-...rcvp) -> SaveToDevice)

# 4. (after config exists / from a decoded capture) send test patterns
sudo python3 colorlight_stock_test.py enx9c69d388d76e 64 64 64

# RE (reference only — path superseded by the Wine capture):
r2 -2 -q -c 's 0x100e57b0; af; pdf' re/dll/CLTDevice.dll   # RcvParamSaveToDevice
```

---

## Key facts & gotchas

- **Panel NIC = `enx9c69d388d76e`** (USB). Built-in `enp4s0` is unusable.
- USB NIC must be in a **USB-C/TB port, directly** (not via hub; not USB-A).
- **Never unplug the WiFi dongle** — it's the only internet/uplink.
- Card: stock firmware **6.0**, MAC `11:22:33:44:55:66`, replies to `0x0700`
  with `0x0805`.
- Colorlight frames: `0x0700` detect → `0x0805` reply; `0x0a` brightness;
  `0x5500` pixel rows; `0x0107` sync/display. Sender MAC `22:22:33:44:55:66`,
  card MAC `11:22:33:44:55:66`.
- Panel is "flash-and-go" hardware-wise (standard DP5125D + SM5166PS), so it
  needs only a correct **standard 1/32 config** — no exotic chip init.
- LEDVISION CDN downloads need a `Referer: https://en.colorlightinside.com/` header.
- **Delete `.env`** (`rm /home/muse/Desktop/LED/.env`) when privileged work is done.
```
