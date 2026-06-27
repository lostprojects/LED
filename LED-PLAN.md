# LED-PLAN.md — A real plan to get the panels working

*Written 2026-06-25 after reviewing all prior work (README, HANDOFF, project
memory, the `re/` RE assets) and researching the open-source Colorlight
ecosystem. Goal: stop the scattergun, pick the shortest honest path to **panels
lit**, and have a clean fallback.*

---

## ⭐ RESEARCH UPDATE (2026-06-27) — go back to Plan A2a (GUI). Two facts settle it.

Fresh online research into how the Colorlight community actually configures these
cards **contradicts the Session-3→6 "sender-topology wall" conclusion** that pushed
us into the 9-session Option-F Unicorn RE. The two load-bearing findings:

**1. Receiver config is a ONE-TIME write to the card's onboard FLASH — not a
per-session stream.** LEDVISION's *"Save to Receiver"* writes scan/routing/gamma
to the receiver's flash chip and **it persists across power cycles** (vs *"Save"*,
which only goes to volatile SDRAM for testing). So we do **not** need a repeatable
Python config-sender at all — we need the card configured **once**, after which the
already-solved open-source **pixel** path (Harald Kubota / kostaman / FPP:
`0x0a` brightness, `0x55` row data, `0x0107` sync) drives it forever.
Source: colorlitled "Configuration Files for Colorlight Receiver Card".

**2. Configuring a receiver DIRECTLY from a PC NIC — with NO sender card — is the
*standard, documented* community workflow.** Thousands of FPP/xLights users do
exactly PC→direct-cable→receiver. The wiredwatts P5 guide: *"Plug your Colorlight
card directly into your Gigabit NIC without anything in between."* The GUI flow:
Screen → Screen Management (set dimensions) → **LED Screen Setting, password `168`**
→ select the PC network card as the sending device → **Detect Receiver Cards** →
Screen Parameters tab → **Load** the `.rcvp` → **Save to Receiver on BOTH the Screen
Parameters AND Receiver Mapping tabs**. No physical sender card anywhere.
Sources: wiredwatts P5 guide, AusChristmasLighting multi-Colorlight FPP guide.

**Why this overturns the wall:** the `0xe0830240 "no current sender"` errors came
from poking the DLLs **cold/headless**, never completing the GUI's Screen-Management
+ NIC-selection that registers the PC NIC **as a software sender**. "Sender" in
LEDVISION ≠ a sender card — it can be the NIC. Session 3 itself flagged the **32-bit
LEDVISION main-app GUI as untested** — that untested path is the exact one the whole
internet confirms works direct-PC-to-receiver. Option F is reinventing what this GUI
does in five clicks, at the most brittle layer possible.

**Corollary nobody open-source has cracked:** every prior project (Kubota, kostaman,
FPP, chubby75) configures via LEDVISION once and only *streams* pixels — Kubota:
*"To configure… you need LEDVISION. Once done, it's no longer required."* So there is
no shortcut around the one-time config except (a) run LEDVISION's GUI, or (b) flash
open gateware (Plan B).

### Revised recommendation
1. **PRIMARY — complete Plan A2a (§3, A2a):** run the **32-bit LEDVISION GUI** on
   `Xvfb :99` (NEVER `:0` — see [[vscode-crash-cause]]), password `168`, select
   `enx9c69d388d76e`, Detect Receiver Cards, load
   `26- full-color thirty-two scan.rcvp`, **Save to Receiver** (both tabs). The
   CLTNic→wpcap→libpcap bridge is already proven (Session 5 `pcaptest2.exe` got the
   `0x0805`). Run `tcpdump -i enx9c69d388d76e -w` throughout → both lights the panel
   AND yields the byte-exact config capture to replay. **Honest caveat:** no
   community precedent for LEDVISION under Wine — the CEF GUI is the risk.
2. **EQUALLY GOOD — borrow a Windows box / VM for ~15 min** with the USB NIC and do
   the same one-time config. Because config persists in flash, this *permanently*
   solves it with zero Wine risk, then stream pixels from Python forever.
3. **STOP Option F** (Unicorn record→wire RE). It reinvents the GUI's job. Keep
   `records.json` / `gen_dests.json` as reference only.
4. **FALLBACK — Plan B (§4):** flash open gateware (~$5 DirtyJTAG) → Art-Net native.
5. **Escape hatch if the Colorlight keeps fighting:** drive HUB75 panels directly
   with **ESP32 (ESP32-HUB75-MatrixPanel-DMA)** or **Pi (hzeller/rpi-rgb-led-matrix)**
   and drop the Colorlight entirely.

*(The rest of this file is the original 2026-06-25 plan; it already led with Plan A —
the research above re-confirms that lead and supersedes the Session-5→9 pivot to
Option F.)*

---

## 0. TL;DR — the decision

We have been trying to **reconstruct LEDVISION's config bytes by hand** —
mapping `.rcvp` files, then hand-emulating the 32-bit Windows DLLs under Unicorn
to dump 270 internal "records", then trying to reverse the record→wire reframing.
That last step is the blocker and it is brittle, deep, and may never converge.

The reason we went down that road was a single assumption:

> *"No Windows; Wine can't do raw Ethernet/Npcap, so we must run the DLL offline."*

**That assumption is false.** Modern Wine (≥1.7.25) ships an upstream
`wpcap.dll` that **forwards WinPcap calls to real Linux `libpcap`**. `CLTNic.dll`
is exactly a WinPcap layer. So we can run the **real, unmodified LEDVISION on
this Linux box under Wine**, point it at our USB NIC, and let it send the **real
config frames to the real card** — then watch the panel light up and/or capture
those frames with `tcpdump` and replay them from Python forever.

This is the user's own framing — *"just port the software from another
platform"* — except we don't even port it: **we run the actual software on
Linux, with its network bridged to the real card.** It sidesteps 100% of the
remaining reverse-engineering.

**Plan A = Wine + wpcap→libpcap bridge (primary).**
**Plan B = flash the open FPGA gateware (fallback, if Wine path fails).**

Everything we've already proven (gigabit link, two-way comms, pixel frames make
the panel react, the `.rcvp` for our exact panel, `records.json`) stays useful.

---

## 0b. Viability VERIFIED (2026-06-25) — Plan A is a go

All Plan-A prerequisites checked and present on this box:

- ✅ **`CLTNic.dll` uses userland WinPcap** (the make-or-break fact). It
  dynamically loads `wpcap.dll` and imports `pcap_open`, `pcap_sendqueue_*`,
  `pcap_next_ex`, `pcap_compile`, `pcap_setfilter`, `pcap_close` (literal string
  `WinpCap` present). Not a kernel NDIS driver → bridgeable.
- ✅ **Wine 9.0** installed (`wine-9.0`, Ubuntu repack) — far past the 1.7.25
  wpcap-support threshold.
- ✅ **The wpcap→libpcap bridge ships and resolves.** Wine 9's split layout:
  `/usr/lib/i386-linux-gnu/wine/i386-windows/wpcap.dll` (PE builtin CLTNic will
  load) + `/usr/lib/i386-linux-gnu/wine/i386-unix/wpcap.so` (unix thunk). The
  thunk links to **`libpcap.so.0.8`**, which we installed
  (`libpcap0.8t64:i386`). Full chain: CLTNic → wine wpcap.dll → wpcap.so →
  libpcap → AF_PACKET on the real NIC.
- ✅ i386 multiarch already enabled; 32-bit GTK/CRT deps pulled in by Wine.

Installed this session (via `.env` sudo): `wine wine32:i386 wine64 winetricks
libpcap0.8t64:i386`. Nothing left to install for Plan A. Next: create a Wine
prefix and do the config send + tcpdump capture (section 3).

### Update (Session 3, 2026-06-25) — A2b harness is walled off; do A2a (32-bit GUI)
Wine transport is fully validated as a runtime: harnesses that `LoadLibrary` the
real DLLs under **both** prefixes load them, resolve every config export, and
enumerate the NIC (`enx9c69d388d76e` = adapter index 1). But the **cold A2b
harness cannot drive a config send**: in the 32-bit DLLs every detect/config
export returns `0xe0830040` because the library's internal **"current sender"
list is empty**, and registering a sender (the NIC binding) is backed by
**persisted screen/sender state that only the LEDVISION GUI's screen-setup
creates** — there is no clean cold-start API for it (RE is open-ended). **So lead
with A2a: run the real 32-bit `LEDVISION.exe` GUI under Wine, set up the NIC
sender, push the `.rcvp`, and capture.** That also persists the sender state that
would later unblock a pure harness. (The prior "GUI is a dead end" note applies
only to the **x64 LEDSetting**; the **32-bit LEDVISION main app is untested in the
GUI** and is the next thing to try.) **⚠️ Run the GUI on `Xvfb :99`, NEVER `:0`,
as root** — LEDVISION's embedded Chromium/CEF on the user's `:0` crashed the
desktop + VSCode before (project memory `vscode-crash-cause`); drive it blindly
via `xdotool` + screenshots and `wineserver -k` after. Full blow-by-blow in
`HANDOFF.md` §"SESSION 3" and the project memory. Sources: `re/wine/h32.c`, `run_h32.sh`.

### Privileged access (documented)
Privileged commands run via **`sudo -S` reading `SUDO_PASS` from
`/home/muse/Desktop/LED/.env`** — the agent is authorized to use it. Rules:
never print the password; don't `cat`/`echo` `.env`; don't feed sudo via a
heredoc on the same command (it steals sudo's stdin — write a script to a file
first). Pattern:
```bash
set +H; set -a; . /home/muse/Desktop/LED/.env; set +a
printf '%s\n' "$SUDO_PASS" | sudo -S -p '' <command>
```
Wine raw-socket capture needs `cap_net_raw`; running the capture session under
this sudo is the simplest route. **`rm /home/muse/Desktop/LED/.env` when the
project is done.**

---

## 1. Where we actually are (honest state)

**Proven working:**
- Gigabit L2 link Linux → 5A-75E via USB NIC `enx9c69d388d76e` (ASIX AX88179B).
  (Built-in `enp4s0` is dead on this T2 Mac — settled, don't revisit.)
- Two-way Colorlight comms: `detect_5a75e.py` sends `0x0700`, card replies
  `0x0805`, **firmware 6.0**, card MAC `11:22:33:44:55:66`.
- Pixel frames make the panel **react** (flicker) → HUB75 outputs are being
  toggled; the data path Linux→card→panel is real.
- We have the **exact config file** for our panel: `re/config_files/General
  Parameters(Fullcolor)/26- full-color thirty-two scan.rcvp` (1/32, 64×64).
- We have LEDVISION 9.2 fully unpacked and its DLLs in `re/dll/`.

**The one blocker:** the card is brand-new and **unconfigured**. Without a valid
receiver config (scan type + routing + remap) it drives the panel with garbage.
We have not yet gotten a valid config onto the card.

**Why the current approach is stuck:** we can *compute* LEDVISION's internal
config (the Unicorn harness produces `records.json`), but turning those internal
records into the exact on-wire Ethernet frames requires reversing a reframe step
that lives in `CLTNic` + a threaded, exception-throwing send path that the
offline emulator can't drive (it deadlocks on a spin-mutex / throws a C++
exception with no EH unwinding). This is the deepest, least reliable possible
place to be fighting.

---

## 2. The key realization that changes everything

Three facts, now verified by research:

1. **Wine forwards WinPcap to libpcap, upstream, since Wine 1.7.25.** A Windows
   app that uses `wpcap.dll` to send/receive raw L2 frames will, under Wine,
   actually send/receive them on a real Linux interface via `libpcap`. (Sources
   below.) This is the exact API family `CLTNic.dll` uses.

2. **The hard problems that broke the offline emulator (C++ exceptions,
   threading, the spin-mutex, the CRT) simply don't exist under Wine** — Wine
   provides the full, real Win32 + CRT + threading environment. The DLL runs as
   its authors intended. The *only* thing we have to bridge is the network, and
   Wine already bridges it.

3. **Colorlight config/firmware is normally pushed over the network anyway**
   (LEDVISION / LEDUpgrade do it over Ethernet). So "configure the card" is a
   network operation that the Wine+libpcap bridge can carry end to end.

**Consequence:** we can get **ground truth** — the literal bytes LEDVISION puts
on the wire to configure *this* card for *this* panel — by capturing them with
`tcpdump` while LEDVISION (under Wine) sends them. No more guessing payloads, no
more reversing the reframe. Capture once → replay from pure Python → Linux-native
forever.

---

## 3. Plan A — Wine + wpcap bridge (primary path)

Order of operations. Stop at the first step where the panel lights — later steps
are only for a clean, permanent, Linux-native pipeline.

### A1. Stand up Wine with the pcap bridge
- Install Wine (32-bit / WOW64) + **32-bit `libpcap`** (LEDVISION DLLs are
  32-bit PE, so the pcap forwarding needs the 32-bit lib).
- Confirm Wine was built with pcap support: look for `wpcap.dll.so` under the
  Wine lib dirs. If present, forwarding is available.
- Raw capture needs privilege. We already run privileged via `.env`/`sudo`;
  simplest is to run Wine as root for the capture session, or `setcap
  cap_net_raw,cap_net_admin+eip` on the Wine loader. (Document whichever we use.)
- Sanity check: run any trivial pcap app (or LEDVISION's adapter-select dialog)
  and confirm it can **enumerate `enx9c69d388d76e`**.

### A2. Get LEDVISION (or a minimal harness) talking to the card
Two sub-options — try the zero-code one first:

- **A2a (zero code): run the real LEDVISION GUI under Wine.** Launch LEDVISION,
  select adapter `enx9c69d388d76e`, and use **Tools → Receiver/Sending card
  config** to load `26- full-color thirty-two scan.rcvp` and **send/save to the
  receiver**. The card is right there on the wire; this may Just Work.
- **A2b (tiny harness) — ⚠️ BLOCKED on cold-start (Session 3):** a cold harness
  can't drive the send because the config exports need a registered NIC "sender"
  that depends on GUI-persisted state (see §0b Session-3 update). Revisit only
  AFTER A2a has run once and persisted that state. Plan was: write a ~30-line
  Win32 `.exe` that `LoadLibrary("CLTDevice.dll")`, then calls the documented
  exports `CLTReceiverRcvParamInitFromFile("26-...rcvp")` →
  `CLTReceiverRcvParamSaveToDevice(...)`. Run *that* under Wine. This is the same
  call sequence the Unicorn harness attempted, but in a real Win32 environment
  where the threading/EH/mutex all work, and with the network actually wired up.
  Gather dependent DLLs alongside (`CLTNic.dll`, `CommonClass.dll`, and any
  VC runtime via `winetricks vcrun*`).

### A3. Capture ground truth (do this regardless of whether A2 lit the panel)
- While A2 sends the config, run:
  `tcpdump -i enx9c69d388d76e -w re/capture/config_send.pcap`
- This `.pcap` is the **authoritative, byte-exact config wire sequence** for our
  panel. It instantly answers every open question: the real per-section frames,
  the command bytes, the section order, any app-level checksum, the
  record→wire reframing — all of it, observed, not guessed.
- Also capture a detect (`0x0700`/`0x0805`) and a pixel test for reference.

### A4. Two good outcomes, both winning
- **If the panel shows a clean image under A2:** we're essentially done with the
  hard part. The card now holds a valid config (it persists — receiver config is
  written to the card). From here it's just streaming pixels (already mostly
  solved) → content → 12 panels.
- **If we "only" captured the frames:** decode `config_send.pcap` and reimplement
  the config send in `config_sender.py` as a static replay (the config is fixed
  for a given panel type — it does not need to be recomputed). Result: a
  **fully Linux-native, no-Wine, pure-Python** config+stream pipeline. Use Wine
  exactly once, for the capture.

### A5. Verify config took
- Re-run `detect_5a75e.py`; the `0x0805` reply config fields should now be
  populated (previously they stayed 0). Panel should be drivable cleanly.

**Why this is the right primary:** lowest effort, no new hardware, no fragile RE,
uses the actual vendor software as the source of truth, and converges to a clean
Linux-only end state. It turns a multi-session binary-protocol RE problem into a
"capture a pcap" problem.

---

## 4. Plan B — flash the open FPGA gateware (fallback)

Use only if Plan A fails (Wine won't run the DLLs, wpcap forwarding is broken in
this Wine build, or the card refuses LEDVISION's config). The 5A-75E is a Lattice
ECP5 board; the open Art-Net gateware is already downloaded
(`colorlight_5a-75e_artnet/`, prebuilt `top.bit`). End state: a fully
Linux-native Art-Net HUB75 controller, LEDVISION never needed again.

The only obstacle was **no JTAG programmer and none purchasable**. Re-examine:

- **B1 — cheap/spare JTAG.** DirtyJTAG runs on an **RP2040 / Raspberry Pi Pico**
  *or* an **STM32 Blue Pill** *or* an **FT232** — check if the user already owns
  any of these (very common to have a Pico or an Arduino-ish board in a drawer).
  If so: wire 4 JTAG pins + 3V3/GND to the board's unpopulated header, then
  `openFPGALoader -c dirtyJtag -f --unprotect-flash top.bit`. ~$0 if a board
  exists. This is the clean, well-trodden path (chubby75 / community).
- **B2 — reflash over Ethernet (no hardware, higher risk).** LEDVISION exposes
  `TransparentSendLoadRcvFpga` / `SlowUpgradeRcvParam`, and Colorlight firmware
  updates normally happen over the network. So in principle the gateware could be
  pushed over Ethernet via the stock bootloader. **Risk: brick** (recoverable
  only with JTAG). Treat as experimental; only attempt with a JTAG recovery
  option in hand. *Note:* if we have Wine working for B2's network push anyway,
  Plan A is strictly easier — so B2 mostly matters only if we have JTAG for
  safety but want to avoid wiring for the normal flash.

Recommendation: if Plan A fails, **check for a spare Pico/Blue Pill first (B1)**;
that's the reliable fallback. B2 is a last resort.

---

## 5. After the card is configured (shared by both plans)

This is the easy, well-supported part — lots of prior art to lean on.

1. **Stream pixels.** We already make the panel react. Reference implementations
   for 5A-75E pixel streaming on Linux: **kostaman/LED_Matrix-1** and **FPP's**
   Colorlight output (FPP's frame layout came from the original protocol RE).
   Align our `bringup_test.py` pixel layout with theirs; get one clean static
   image, then a moving test pattern.
2. **Render the menu.** Draw the menu to a framebuffer (Pillow/cairo/skia →
   RGB888), push frames at panel refresh.
3. **Scale to 12 panels.** Build the full canvas (e.g. arrangement TBD — confirm
   physical layout with user) and map each panel to its region + orientation.
   With the open gateware (Plan B) this is Art-Net universes; with stock
   firmware (Plan A) it's the per-card routing in the config + pixel offsets.

---

## 6. What to STOP doing

- **Stop trying to crack the record→wire reframing by static RE / Unicorn.** Plan
  A's pcap capture gives those exact bytes for free. Keep `re/emu/harness.py` and
  `records.json` as *reference* only; do not invest more in driving `Nic_Write`
  under emulation.
- **Stop blind-tuning config payloads** against the live card. We'll have ground
  truth instead of guesses.
- **Don't over-spawn parallel agents** (standing user preference). This is now a
  focused, mostly-linear task.

---

## 7. Open risks / unknowns (be honest)

- **Will LEDVISION run under Wine?** It's a large MFC app; the GUI may be clunky.
  Mitigation: the A2b minimal harness avoids the GUI entirely — we only need the
  DLL exports, which are small and documented.
- **Is *this* Wine build compiled with pcap support / is 32-bit libpcap
  available on Mint 22.3?** Must verify `wpcap.dll.so` exists. If the distro Wine
  lacks it, install a Wine build that has it (WineHQ packages do).
- **Does CLTNic actually call `wpcap` (vs a custom raw driver)?** The notes say
  it's a "WinPcap L2 layer." Confirm by dumping CLTNic's import table
  (`pcap_*` / `wpcap.dll` imports). If it imports `wpcap`, the bridge applies
  directly. (If it ever used a kernel NDIS driver we'd fall back to Plan B — but
  WinPcap userland is the documented design.)
- **Permissions:** raw capture under Wine needs `cap_net_raw`. We have sudo.
- **Plan B brick risk** for the over-Ethernet flash (B2) — gated behind having a
  JTAG recovery path.

None of these block *starting*; A1's verification step resolves the biggest two
quickly.

---

## 8. Immediate next steps (concrete)

1. `apt`-install Wine (WOW64) + 32-bit `libpcap`; confirm `wpcap.dll.so` exists.
2. Dump `CLTNic.dll` imports to confirm it uses `wpcap`/`pcap_*`.
3. Try A2a: LEDVISION GUI under Wine → select `enx9c69d388d76e` → load the
   `26- ...thirty-two scan.rcvp` → send to receiver, with `tcpdump` capturing.
4. If GUI is unworkable, build the A2b minimal harness exe and run that.
5. Watch the panel; verify with `detect_5a75e.py`; save the capture under
   `re/capture/`.
6. Decode the capture → static-replay config in `config_sender.py` (Linux-native).
7. Clean image → menu render → scale to 12.

---

## 9. References (open-source ecosystem & key facts)

- Wine forwards `wpcap.dll` → libpcap (upstream since Wine 1.7.25):
  <http://dawncrow.de/wine/wpcap.html>, WineHQ forum threads on WinPcap/Wine.
- **kostaman/LED_Matrix-1** — Linux L2 sender for 5A-75B/5A-75E (pixel path
  reference): <https://github.com/kostaman/LED_Matrix-1>
- **q3k/chubby75** — 5A-75E hardware RE (FPGA, JTAG header, flashing):
  <https://github.com/q3k/chubby75> ·
  <https://github.com/q3k/chubby75/blob/master/5a-75e/README.md>
- **Harald Kubota — Colorlight 5A protocol RE** (display/pixel protocol):
  <https://hkubota.wordpress.com/2022/01/31/winter-project-colorlight-5a-75b-protocol/>
- **roby2014/ecp5-ft232rl-example** — flashing 5A-75E via FT232RL/JTAG, open
  toolchain: <https://github.com/roby2014/ecp5-ft232rl-example>
- **chmousset/colorlight_reverse** — RE of related Colorlight receiver cards:
  <https://github.com/chmousset/colorlight_reverse>
- FPP (Falcon Player) Colorlight output — pixel-streaming reference on Linux.
- **Config is one-time-to-flash + direct-PC-NIC config is the documented norm
  (2026-06-27 research):**
  - colorlitled — "Save to Receiver" writes to flash, persists across reboots:
    <https://www.colorlitled.com/configuration-files-colorlight-receiver-card/>
  - wiredwatts — direct PC NIC → receiver, no sender card, password-168 flow:
    <https://www.wiredwatts.com/colorlight-setup-for-outdoor-p5-panels>
  - AusChristmasLighting — multi-Colorlight FPP guide (Screen Management →
    Detect → Save to Receiver, both tabs):
    <https://auschristmaslighting.com/threads/multiple-colorlight-cards-with-fpp-for-p5-panels-guide.11762/>
- **Direct-drive escape hatch (skip Colorlight):** ESP32-HUB75-MatrixPanel-DMA;
  hzeller/rpi-rgb-led-matrix (Raspberry Pi).
- Local RE assets: `re/dll/CLTDevice.dll`, `re/dll/CLTNic.dll`,
  `re/config_files/.../26- full-color thirty-two scan.rcvp`, `re/data_emu.txt`,
  `re/emu/records.json` (keep as reference).
