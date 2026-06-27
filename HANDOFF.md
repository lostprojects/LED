# Agent handoff prompt

> **⚠️ ARCHIVE (Sessions 1–6) — not the current task.** The current handoff is
> [`HANDOFF-S9.md`](HANDOFF-S9.md); current progress is
> [`OPTION-F-PROGRESS.md`](OPTION-F-PROGRESS.md). This file is kept only for deep
> background. The Wine/live-DLL route it discusses is settled-dead (see
> `SENDER-WALL-RECOMMENDATION.md`); some files it links (`SENDER-WALL-BRIEF.md`,
> `DYNAMIC-PROBE-BRIEF.md`) were deleted as outdated.

Copy everything below the line into a new agent session working in
`/home/muse/Desktop/LED/`.

---

You are taking over a hardware-bringup + reverse-engineering project on a Linux
Mac mini. Read `README.md` first (full context), then this prompt (quick-start +
exact next task). Deep background lives in the project memory at
`/home/muse/.claude/projects/-home-muse-Desktop-LED/memory/led-bar-menu-project.md`
— read it, it has the full blow-by-blow.

## The project in one paragraph

Build a bar menu from **12× 64×64 HUB75 LED panels** driven by a **Colorlight
5A-75E** receiver card from this Linux Mac mini. The card talks raw Layer-2
Ethernet (no IP). Gigabit link + two-way comms work. The card is brand-new and
**unconfigured**, so it won't cleanly drive the panel yet. The remaining piece is
getting a valid receiver config onto the card.

> **READ [`LED-PLAN.md`](LED-PLAN.md) FIRST — it is the plan of record (2026-06-25).**
> We pivoted away from hand-reversing LEDVISION's DLLs (the Unicorn/`records.json`
> path below stalled on the record→wire reframe). **New primary (Plan A): run the
> real LEDVISION under Wine** — Wine forwards `wpcap.dll`→Linux `libpcap`, and
> CLTNic is a WinPcap layer, so the real software configures the real card over
> `enx9c69d388d76e` and we `tcpdump` the exact frames. **Verified viable + Wine
> installed (2026-06-25).** The DLL-RE material below is now REFERENCE ONLY.
>
> ### ⚠️ SESSION 5 (2026-06-26) — read [`SENDER-WALL-BRIEF.md`](SENDER-WALL-BRIEF.md) — THE current task
> Plan A's runtime is proven (wpcap bridge works under **x64 Wine**; the real x64
> **`LEDSetting.exe`** runs on **Xvfb :99 + openbox**, never :0). We **fixed the x64
> WinPcap gate** (regkey must be in the **64-bit** view: `wine reg add … /reg:64`),
> and `CLTReceiverRcvParamInitFromFile(.rcvp)=0` loads under real Wine. **But the
> tool is walled at "register a sender":** the CLTDevice manager's "current sender"
> (`vtbl+0x128`) is NULL on a cold prefix → `CLTReceiverDetectAll`/`SaveToDevice`
> bail `0xe0830240/0241` BEFORE any NIC I/O, and `Nic_SenderStart` fails `0xe0831204`
> because the screen has no assigned adapter NAME to match the (populated) adapter
> list. The single remaining blocker = **bind the PC NIC as a sender / assign it to a
> screen**. Full RE state + ranked options are in **`SENDER-WALL-BRIEF.md`**; next
> agent should produce `SENDER-WALL-RECOMMENDATION.md` then execute the best option.
> Staged harnesses live in `.wine-led64/drive_c/LEDSetting/x64/Bin/`
> (`pcaptest2 hwp h3 cap cap2 cfg.rcvp`); sources in `re/wine/*.c`.

## Hard constraints (do not violate)

- **No Windows; don't propose it.** (Wine for *raw Ethernet/Npcap* is out. NOTE:
  using an emulator/Wine purely to run DLL *computation offline* is fine and is
  exactly what we did — see below — but no networked Windows.)
- **No JTAG/FTDI/Pico/CH341A programmer and none can be bought.** Flashing the
  open gateware (Path B) is a fallback only if such hardware ever appears.
- **Panel NIC = USB adapter `enx9c69d388d76e`** (ASIX AX88179B). Built-in
  `enp4s0` is dead under Linux (T2 Mac) — never use it; settled.
- **Never unplug/move the USB WiFi dongle** — only internet uplink + your link to
  the user. The USB-Ethernet adapter must stay in a USB-C/TB port, plugged direct.
- Root for raw sockets. `/home/muse/Desktop/LED/.env` has `SUDO_PASS`. Use it
  **without printing it**, and NOT via a heredoc on the same command (the heredoc
  steals sudo's stdin — write the script to a file first):
  ```bash
  set +H; set -a; . /home/muse/Desktop/LED/.env; set +a
  printf '%s\n' "$SUDO_PASS" | sudo -S -p '' python3 /path/to/script.py ...
  ```
  Don't `cat`/echo `.env`. Remind the user to `rm .env` when the project is done.
- **Don't over-spawn parallel subagents** (user preference). Do the RE directly.
- **NEVER launch a Wine GUI (LEDVISION/LEDSetting) on `DISPLAY=:0` as root.**
  LEDVISION embeds Chromium/CEF (92MB `libcef.dll`); a root GPU client on the
  user's `:0` session fights VSCode's Electron and **crashes the desktop +
  VSCode**. The GUI route is a confirmed dead end anyway (see Session 2). Use the
  **headless A2b harness only** (no windows). If a GUI is ever unavoidable, render
  it to an **Xvfb virtual display (`:99`), never `:0`**, and kill the wine tree
  after (`wineserver -k`) so orphans don't pile up and saturate the 4-core box.

## THE BIG WIN THIS SESSION — we can run CLTDevice.dll's serializer offline

We built a **Unicorn x86-32 emulation harness** at **`re/emu/harness.py`** that
loads `CLTDevice.dll`, parses a `.rcvp`, and runs the DLL's OWN serializer to dump
the **byte-exact serialized config** LEDVISION computes. Output is **270 "frame
records"** in **`re/emu/records.json`**. This is the authoritative config data
(the old approach of slicing raw `.rcvp` bytes was wrong — the DLL reformats them).

Run it:  `cd re/emu && python3 harness.py`  (takes ~1–2 min; writes records.json).
Tooling already installed: `python3-unicorn python3-capstone python3-pip` (apt) +
`pefile` (pip --break-system-packages).

**What it took to get the DLL running under emulation (all solved in harness.py,
don't redo — read the code + comments):** map DLL at 0x10000000 (no reloc); 256MB
stack + bump heap; **FS/TEB via a full flat GDT** (must reload CS/DS/SS/ES to flat
selectors AND set FS base=TEB — Unicorn 32-bit ignores the FS_BASE reg, and just
setting GDTR truncates SS); skip CRT `_DllMainCRTStartup`, instead call singleton
ctor `0x100fac00` + set export guard `[0x1028a670]=1`; patch CRT globals
(`__acrt_heap`@`0x10289900`=fake handle; lock table @`0x102784a8` ×128 non-null so
EnterCriticalSection-as-noop doesn't recurse; real TLS dict; scan+patch the ~24
"encoded fn-ptr" globals `mov eax,[g]; xor eax,[cookie]; je; call eax` = cookie;
Encode/DecodePointer = xor cookie); locale **GetACP=1252 (NOT 936 DBCS, which
stack-smashes)** + GetCPInfo MaxCharSize=1; serve the .rcvp via CreateFileW/
ReadFile hooks. Then: getter `0x10102b40`(ecx=`0x1028a680`) → **CReceiverOP**;
**deserialize via `fcn.100945f0`(this=`[CReceiverOP+8]`=codec, buf, len, 0)=0 OK**
(bypasses the ifstream/file path); **GetSaveCMDData** export `0x100e40d0` →
CReceiverOP vtable+0x64 `0x101a6480` → worker `0x10190dd0`(this=`[CReceiverOP+0x10]`,
out_obj={[8]=[0xc]=recbuf,[0x10]=recbuf+size}) → **builds the 270 records.** (The
C++ exception at the very end is post-build cleanup; the data is already valid.)

### The 270 records (re/emu/records.json)
Each record = 0x60c struct: `body[0..len]`, `+0x600`=u32 len(=266), `+0x604`=u32
code (`0xbb8`=section header / `0x06`=data). Body layout (framer `fcn.10194b00`):
`[b0=06/26][00 00][26][00][b5=23 hdr / 85 data][00][b7=section code][b8=block idx][00] + ≤256B payload`.
Grouped by b7 into 3 sections: **0x09** (11 rec → 2560B, gamma/calib floats),
**0x07** (224 rec → 57088B, basic-param + routing + LUTs; has identity col-remap
`40 41 42…`, scan/route LUT `20 00 20 01…`), **0xe9** (35 rec → 8704B, `01 ff ff…`).
These are the **flash/SAVE-protocol 256B-block records** — a DIFFERENT family from
the `data_emu` DISPLAY frames (cmd 0x05/0x18/0x03…).

## What else is SOLVED (don't redo)

- **Wire frame format of the DISPLAY path** (from `re/data_emu.txt`, Colorlight's
  own auto-gen receiver sim): after MACs, `byte12=CMD, byte13-14=serial(u16 BE),
  byte15=subframe, byte16+=payload`. CMDs: 0x05 basic, 0x18 scan, 0x03 route,
  0x02 cardarea, 0x10 void, 0x01 switch, 0xFF init, 0x55 pixels. Sender MAC
  `22:22:33:44:55:66`, card MAC `11:22:33:44:55:66`. BUT data_emu's section
  payloads are template placeholders (`#-BASICPARAM-#`) we can't auto-fill.
- **`.rcvp` container** mapped (magic, fixed basic block @0x18, length-prefixed
  sections `[u16 len][0x07 tag][idx]`, trailing checksum). See memory for detail.
- **DLL call-path** mapped (singleton @0x1028a680, CReceiverOP, codec, save/send
  workers, sendCmd `0x100eeed0` is the only Nic_Write caller). See memory.
- Detection works: `0x0700` → card replies `0x0805` (1070B, fw 6.0). Carrier=1.

## THE BLOCKER — record→wire framing is still unknown

The records are the DLL's INTERNAL format. The on-wire Ethernet frame is produced
by a **reframe step in CLTNic + a threaded/throwing send path** we can't yet drive
in the emulator. The literal card MAC `11:22:33:44:55:66` appears in NEITHER
CLTDevice nor CLTNic → **CLTNic frames at runtime.** Empirically PROVEN that the
naive framing is WRONG: `config_sender_v2.py` sent all 270 records as
`[dst][src]+record_body` to the live card → **zero acks** (card ignores
byte12=0x06/0x26), 0x0805 only ticks its counter @0x3c-0x3e. So the reframe
(internal code → real wire cmd) is the missing ~5%.

Why we couldn't just capture Nic_Write: `SaveToDevice` (export `0x100e57b0` →
CReceiverOP vtable+0x54 `0x101a5b80` → transport vtable+0x2d0) **deadlocks on a
spin-mutex** (acquire `fcn.101f090e`; harness already hooks it to no-op-acquire),
then **throws a C++ exception 0xe06d7363** (from `fcn.100fb1f0` area) because with
args `[0,0,0,0,0]` no real NIC/port is selected, and the harness has no C++ EH
unwinding. CLTNic `Nic_Write` real impl = `0x10002fb0` (NIC obj @`[0x101b16b0]`,
calls a pcap-send fn-ptr `[this+0x20]`). GetSendCMDData (display path, export
`0x100e4080`) is NOT the config path — it's pixel/display data, returns empty here.

## ⭐ SESSION 2 (2026-06-25) — Plan A VALIDATED at transport; now building a harness

Big progress. Read this before anything below it.

**Wine + wpcap bridge PROVEN end-to-end.** Built a Win64 prefix at
`/home/muse/Desktop/LED/.wine-led64` (root-owned; pcap needs root). A tiny mingw
probe (`re/wine/pcaptest2.exe`, src `pcaptest2.c`) loaded `wpcap.dll`, opened
`enx9c69d388d76e`, sent the real 0x0700 detection frame, and **got the card's
0x0805 reply (fw 6.0, 1070B) back through Wine.** So Wine's wpcap→libpcap carries
full bidirectional Colorlight L2 to the live card. Plan A's transport works.

**Tooling installed this session:** `xdotool` (drive the GUI), `mingw-w64`
(`x86_64-w64-mingw32-gcc`, compile harnesses), winetricks `vcrun2013`+`vcrun2019`
into BOTH prefixes. `.wine-led` = win32 prefix w/ LEDVISION (32-bit). `.wine-led64`
= win64 prefix w/ **LEDSetting** (the real config tool). Screenshots via
`xfce4-screenshooter -f -s <png>`; render to the user's screen with
`DISPLAY=:0 XAUTHORITY=/home/muse/.Xauthority` (root can read it).

**GUI route is a DEAD END under Wine (don't sink more time):** LEDVISION's
"Control ▸ LED Screen Settings" spawns a separate **x64 `LEDSetting.exe`**
(found at the NSIS payload `$_15_/x64/Bin/LEDSetting.exe`; copied into
`.wine-led64/drive_c/LEDSetting`). LEDVISION's spawn fails ("LEDSetting start
failed!"). Running `LEDSetting.exe` *directly* works and shows its launcher
(Device Information / Display Settings / Screen Configuration / Test Tool / …).
BUT the **network-dependent modules (Device Information, Screen Configuration)
never open and LEDSetting never scans the NIC** (tcpdump shows zero Colorlight
frames; only host DHCP/mDNS). Display Settings (local-only) does open. Root cause
is almost certainly CLTNic's adapter init not running in the GUI flow (see below).
Not worth more GUI poking — the harness is the path.

**THE PATH = harness (A2b), disassembly-driven, and it's working.** Real Wine has
full CRT/threading/EH, so calling CLTNic/CLTDevice exports directly is viable.
Compile with mingw, drop the .exe in `.wine-led64/drive_c/LEDSetting/x64/Bin/`
(so it finds the sibling DLLs), run under that prefix. Use `r2 -2` on the **x64**
`CLTNic.dll`/`CLTDevice.dll` in that Bin dir to recover signatures (no headers).
Verified working harness `re/wine/h2.exe` (src `h2.c`):
- `Nic_GetNetAdapterCount(int* outCount, BOOL refresh)` — **must pass refresh=1**
  to enumerate (else count stays 0; that's why the cold h1 probe failed).
- `Nic_GetNetAdapterInfo(int idx, char* name, int nameBufSz, char* desc,
  int descBufSz, short* outType)` — the two `int`s are **dest buffer sizes**
  (NOT codepages); pass 260. Returns GUID in `name`, iface in `desc`.
- Result: 2 adapters; **`enx9c69d388d76e` is adapter index 1** (GUID
  `{00000002-0000-0000-0000-4E6574446576}`). adapter[0]=enp4s0.

**NEXT (resume here):** RE + call the config-send chain in the harness, tcpdump
capturing on enx the whole time:
1. Find how a NIC is *bound* for sending (so CLTNic uses enx, index 1). Candidates
   in CLTNic: `Nic_CreateScreen`, `Nic_SenderStart`, `Nic_SetSendParamScreenNumber`,
   `Nic_NetAdapterIDExist`; in CLTDevice: `CLTSetTargetDevice`,
   `CLTChangeCurDeviceSet`. Disassemble to get their sigs.
2. `CLTReceiverDetectAll`/`CLTReceiverDetectOne` → `CLTReceiverGetCount` to find the
   live receiver on enx (proves binding worked; should emit 0x0700 / get 0x0805).
3. `CLTReceiverRcvParamInitFromFile("…/26- full-color thirty-two scan.rcvp")` then
   **`CLTReceiverRcvParamSaveToDevice(...)`** — the actual config push. This is the
   one the old Unicorn attempt died on; under real Wine it should run. Its args are
   unknown — disassemble (export in the x64 CLTDevice) and iterate.
4. The instant SaveToDevice sends, **tcpdump has the byte-exact config frames** =
   ground truth → decode → static-replay from pure Python (`config_sender.py`),
   Linux-native forever. And the panel should light.

tcpdump capture file in progress: `re/capture/config_send.pcap` (started this
session; currently only host noise — restart it right before the config send).
All harness sources + screenshots live in `re/wine/`.

Privileged runs use the `.env` sudo pattern. Prefix wine cmds with:
`export WINEPREFIX=/home/muse/Desktop/LED/.wine-led64 WINEARCH=win64 HOME=/root WINEDEBUG=-all`

## ⭐ SESSION 3 (2026-06-25) — harness path mapped to a precise wall; GUI is the way

Read this; it supersedes SESSION 2's "build the harness" plan.

**Wine works as a runtime on BOTH prefixes.** Tiny mingw harnesses
(`LoadLibrary` the real DLLs, call exports) confirm: `.wine-led64` (win64,
LEDSetting) and `.wine-led` (win32, LEDVISION) — both **root-owned**, run with
`HOME=/root WINEDEBUG=-all` — load the DLLs, resolve all config exports, and
`Nic_GetNetAdapterCount(&n, refresh=1)` enumerates **[0]=enp4s0,
[1]=enx9c69d388d76e**. Harnesses in `re/wine/`: `h2.exe` (x64 enum, works),
`h3.c/exe` (x64 detect), **`h32.c/exe` (32-bit detect)**. Capture wrappers
`run_h3.sh`/`run_h32.sh`. **Gotcha:** don't pipe a run script's stdout into
`head`/`grep` — the backgrounded `tcpdump` inherits the pipe and hangs the
pipeline; redirect to a file.

**The 32-bit LEDVISION DLLs are the right target** (much simpler than x64
LEDSetting; their exports are decorated with stdcall arg-byte counts = free
signatures): `_CLTReceiverDefaultDetectAll@8` (= DetectAll w/ a default param
struct), `_CLTReceiverGetCount@0`, `_CLTReceiverRcvParamInitFromFile@4`
(1 ptr = path), `_CLTReceiverRcvParamSaveToDevice@20` (5 args). Call model
(base 0x10000000): export → singleton @0x1028a680 (vtable 0x1024cdd4) → manager
via `vtbl[0x94]` (detect) / `vtbl[0xac]` (rcvparam). **No device-set layer**
(unlike x64).

**PRECISE BLOCKER:** every detect/config call returns **`0xe0830040`**. The
manager getter fcn.10102a80 first needs a **"current sender"**
(`singleton.vtbl[0x3c]`=fcn.100fb940), but the **sender vector at singleton+8 is
EMPTY**. The sender-refresh (fcn.100fb1f0 → fcn.101030d0) **reads PERSISTED
config** and returns false on a cold prefix. **⇒ Detection/config require a
registered NIC "sender", and that registration is backed by persisted
screen/sender state that only the LEDVISION GUI's screen-setup creates.** There
is no clean cold-start API; RE-ing it is open-ended. **So the cold A2b harness is
walled off behind GUI state.**

**NEXT (do this): A2a — the 32-bit LEDVISION GUI.** Prior session's "GUI is a
dead end" was only tested on **x64 LEDSetting**; the **32-bit LEDVISION main app
(`.wine-led/drive_c/LEDVISION/LEDVISION.exe`) has NOT been GUI-tested.** Run it
under Wine to `:0`, create/select the NIC sender, open Screen/Receiver config,
load `re/config_files/General Parameters(Fullcolor)/26- full-color thirty-two
scan.rcvp`, send to receiver — with `sudo tcpdump -i enx9c69d388d76e -w
re/capture/config_send.pcap` running and the panel powered. Two wins as before:
panel lights, or decode the pcap → static Python replay (`config_sender.py`).
Doing it once also persists the sender state that would unblock a pure harness
later.

**⚠️ DISPLAY CONSTRAINT (hard rule — see project memory `vscode-crash-cause`):**
do NOT launch the Wine GUI on `DISPLAY=:0` as root — LEDVISION embeds Chromium/CEF
and a root GPU client on the user's `:0` crashes the desktop + VSCode. **Run the
GUI headless on `Xvfb :99`** (`Xvfb :99 -screen 0 1920x1080x24 &`, then
`DISPLAY=:99`), drive it blindly with `xdotool`, screenshot with
`xfce4-screenshooter -f -s <png>` (or `import -window root`), and **`wineserver -k`
after**. The panel lighting is physical (independent of the X display), so a
virtual display is fine. Watch for `rg`/`wine` CPU storms; kill orphans with
`wineserver -k` (never `pkill -f 'wine '` — it SIGKILLs the parent shell).

## ⭐ SESSION 4 (2026-06-25) — headless harness advanced; found the WinPcap-regkey gate; wall is the screen→adapter "current adapter"

Read this; it advances SESSION 3 and partially reopens the GUI.

**NEW HARNESS `re/wine/h4.c` (+ `run_h4.sh`) — the 32-bit CLTNic send-path cold-start, mapped & partly working.** Sequence proven on the live box (win32 `.wine-led` prefix):
- `Nic_GetNetAdapterCount(&n,1)` → 2 adapters ([0]=enp4s0, [1]=enx9c69d388d76e). Populates the adapter list `[0x101b1618]`/count`[0x101b161c]` (worker `0x10004650`).
- `Nic_CreateScreen(screenNo=1, w=64, h=64, RESERVED=0, e4∈0..3, e5∈0..3)` → **0x0 OK** (arg3 MUST be 0; it is NOT an adapter ptr — that was a wrong guess. e4/e5 are NOT the adapter index either — swept 0/1, no effect). Screen obj stores screenNo@+0,w@+4,h@+8,e4@+0xc,e5@+0x10; **no adapter field.**
- `Nic_GetScreenCount` → 1; `Nic_SetSendParamScreenNumber(1)` → **0x0 OK** (selects current screen; gates match screens by screenNo@[obj+0]).

**THE WINPCAP-REGKEY GATE (important, reusable — see memory `colorlight-wine-winpcap-regkey`).** `Nic_DetectIsInstallWinpCap`→`fcn.10005180` is just `RegOpenKeyExW(HKLM,"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\WinPcapInst")`; missing key ⇒ CLTNic thinks WinPcap absent ⇒ refuses to open the NIC. **FIXED**: `wine reg add` that key into `.wine-led` (done; `DetectIsInstallWinpCap` now returns 0=success). **This likely also explains Session 2's "GUI never scanned the NIC"** — same missing key, not a GUI bug. If using the x64 LEDSetting prefix `.wine-led64`, add the key there too.

**THE REMAINING WALL (confirmed empirically).** `Nic_SenderStart(1)` still fails **0xe0831204**: it resolves the screen's adapter via a "current adapter" held in CLTNic's manager singleton (`fcn.1000a2bd`; resolver `fcn.10002250`→`fcn.10009f02(screenNo)`). That current-adapter has **NO setter export** — only the GUI's NIC-picker populates it. So a pure-export cold-start is walled exactly here. `CLTReceiverDefaultDetectAll` still 0xe0830040 (same root cause); 0 frames on enx.

**TWO WAYS FORWARD (user paused here 2026-06-25, chose "stop for now"):**
1. **GUI on Xvfb :99** — now that the regkey gate is fixed, run the **32-bit LEDVISION** (`.wine-led`, key already added) on Xvfb `:99` (NEVER :0 — crashes VSCode, see [[vscode-crash-cause]]), drive via xdotool, load `re/config_files/General Parameters(Fullcolor)/26- full-color thirty-two scan.rcvp`, send, `tcpdump -i enx9c69d388d76e -w`. Highest odds of lighting the panel; blind-drive is fiddly. (This supersedes the "A2a retired" note below, which was only about the *x64 LEDSetting*, never the 32-bit LEDVISION GUI.)
2. **Stay headless** — find/poke CLTNic's internal "set current adapter" (no export): either call the setter `fcn.*` by address from h4, or write the adapter entry (`[0x101b1618][1]`) into the manager's current-adapter field directly. More RE, but keeps it Linux-native with no GUI.

---

## Your task — see [`SENDER-WALL-BRIEF.md`](SENDER-WALL-BRIEF.md) (Session 5, current).

**The current, focused task is in `SENDER-WALL-BRIEF.md`:** analyze the ranked
options to *register the PC NIC as a sender* (the one remaining blocker), write
`SENDER-WALL-RECOMMENDATION.md`, then execute the best low-risk path. The steps
below are the older Session-2/4 framing — superseded by the Session-5 brief but
kept for the exact harness/command details.

Everything about the 270 records, the record→wire reframe, and emulating
`Nic_Write` under Unicorn is **REFERENCE ONLY — do not resume it.** Verified
prerequisites (2026-06-25/26): CLTNic is userland WinPcap; **wine-9.0** with both
the 32-bit *and* 64-bit `wpcap.so`→`libpcap` bridge present and **proven working
(x64)**. Nothing left to install.

Do this:

1. **Create a 32-bit-capable Wine prefix** and gather LEDVISION's DLLs +
   VC runtime (`winetricks vcrun*` as needed). Confirm Wine can enumerate
   `enx9c69d388d76e` via the wpcap bridge.
2. **Send the config to the live card**, panel powered, user watching, while
   capturing: `sudo tcpdump -i enx9c69d388d76e -w re/capture/config_send.pcap`.
   - **A2b (THE path — headless, no GUI):** extend the working harness
     `re/wine/h2.exe` (src `h2.c`) — LoadLibrary CLTDevice.dll, bind NIC index 1,
     call `CLTReceiverRcvParamInitFromFile` → `CLTReceiverRcvParamSaveToDevice`;
     run under the `.wine-led64` prefix. See the "SESSION 2 ▸ NEXT" steps above.
   - **A2a (GUI):** the *x64 LEDSetting* GUI is retired (dead end) and NEVER run any
     Wine GUI on `:0` (crashes VSCode). BUT see **SESSION 4**: the *32-bit LEDVISION*
     GUI was never properly tested and was probably only blocked by the missing
     WinPcap regkey (now fixed) — it's a live option **on Xvfb `:99` only**.
3. **Two good outcomes:** panel shows a clean image (≈done) OR decode the `.pcap`
   and static-replay the config from pure Python (`config_sender.py`) → fully
   Linux-native, Wine used once. Verify config took via `detect_5a75e.py` (0x0805
   config fields should populate).
4. Then drive menu content (stream pixels; lean on kostaman/LED_Matrix-1 + FPP)
   and scale to 12 panels.

If Plan A fails, fall back to Plan B (flash open gateware) — check for a spare
Pico/Blue Pill/FT232 for DirtyJTAG first. See `LED-PLAN.md` §4 + `SETUP.md`.

Keep `LED-PLAN.md`, `README.md`, and the project memory updated. Privileged cmds:
use `.env` sudo (`LED-PLAN.md` §0b) — never print it. Be honest about uncertainty.

## Quick commands
```bash
cat /sys/class/net/enx9c69d388d76e/carrier                 # want 1
sudo python3 detect_5a75e.py enx9c69d388d76e               # CARD FOUND 0x0805, fw 6.0
# --- Plan A (current) ---
wine --version                                             # wine-9.0 (installed)
ls /usr/lib/i386-linux-gnu/wine/i386-unix/wpcap.so         # the wpcap->libpcap bridge
sudo tcpdump -i enx9c69d388d76e -w re/capture/config_send.pcap &   # capture config send
# then run LEDVISION (or the A2b harness) under wine; select enx9c69d388d76e; send the .rcvp
# --- reference only (superseded) ---
cd re/emu && python3 harness.py                            # rebuild records.json (REF ONLY)
sudo python3 config_sender_v2.py enx9c69d388d76e           # send records (REF ONLY, framing WIP)
# decompile in radare2 (CLTDevice base 0x10000000, CLTNic base 0x10000000):
r2 -2 -q -e scr.color=0 -c 'af @ 0x10002fb0; pdf @ 0x10002fb0' re/dll/CLTNic.dll
r2 -2 -q -e scr.color=0 -c 'af @ 0x100eeed0; pdf @ 0x100eeed0' re/dll/CLTDevice.dll
```

Reminder: tell the user to `rm /home/muse/Desktop/LED/.env` when the project is done.

---

## SESSION 6 (2026-06-26) — dynamic probe DONE; x64 refresh RULED OUT

Ran the DYNAMIC-PROBE-BRIEF experiment. Built `re/wine/probe.c`→`probe.exe`
(extends cap2.c) which calls the device-manager **refresh `vtbl[0x10]` directly**
(`GetHwDeviceManager` → `vt[2]`, confirmed runtime rva 0x154f70 = `fcn.180154f70`),
then re-checks the detect exports. Run wrapper `re/wine/run_probe.sh`.

**RESULT (read-only, panel idle):** `refresh(mgr,0)` and `refresh(mgr,1)` both
return **`0xe0830101`** with **zero `Nic_Write`, zero `Nic_Read`, 0 frames on the
wire** (empty `probe_*.pcap` + empty `nicwrite_frames.txt`), `GetCount`=0,
`DetectAll` still `0xe0830240`. So: **refresh emits NO raw-L2; NO device registers.**

**Why:** the readiness gate `fcn.18015e5e0` PASSED (gate-fail returns `0xe083123b`,
which we did NOT get), so refresh entered its detection block — which is
**winsock/IP-based** (CLTDevice imports `ws2_32`: WSAStartup ord 23, socket/recv
ords) and never calls the raw-L2 CLTNic path. `0xe0830101` propagates from a socket
callee. → **Decision Rule branch #3: the x64 LEDSetting DLL is the WRONG
abstraction for our PC→raw-L2-receiver topology. STOP pursuing it.** The whole DLL
stack assumes a sender-card (IP/winsock) topology; we talk to the receiver raw-L2
directly, so every DLL path hits the "no sender registered" wall.

**NEXT (see `SENDER-WALL-RECOMMENDATION.md`):** (1, recommended) **Option F** —
finish the config wire-format RE directly and replay from Python, using
`re/data_emu.txt` (authoritative DISPLAY format) + `re/emu/records.json` (270 SAVE
payloads) + working raw L2 send/recv; the gap is the record→wire reframe + section
order + checksum. (2, robust fallback) **Plan B** — flash open gateware (needs a
~$5 DirtyJTAG programmer we don't have). DROP all DLL-driven paths.

Note: ~21 stale `tcpdump` orphans from prior sessions linger in `S` state and
cannot be killed even as root (sandbox/namespace artifact) — harmless, ignore.
