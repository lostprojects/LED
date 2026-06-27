# Agent handoff — Session 9 (finish Option F: capture the data_emu VHDL)

Copy everything below the line into a new agent session working in
`/home/muse/Desktop/LED/`.

---

You are continuing a hardware-bringup + reverse-engineering project on a Linux Mac
mini: build a bar menu from **12× 64×64 HUB75 panels** driven by a **Colorlight
5A-75E** receiver over **raw Layer-2 Ethernet** (no IP). Detection + two-way comms
already work; the card is unconfigured and won't drive panels until we push a valid
config. We are on **Option F**: obtain the **byte-exact `data_emu` DISPLAY wire
frames** and replay them from pure Python.

## Read these first (in order)
1. `OPTION-F-PROGRESS.md` — full writeup of the generator path, what Session 8
   solved, and the exact remaining blocker. **Start here.**
2. Project memory `/home/muse/.claude/projects/-home-muse-Desktop-LED/memory/` —
   read `MEMORY.md` index, then `colorlight-data-emu-generator.md`,
   `led-bar-menu-project.md`.
3. `HANDOFF.md` (older sessions, reference) and `SENDER-WALL-RECOMMENDATION.md`
   (why the live-DLL/Wine routes are dead — DON'T reopen them).

## The strategy (settled, don't relitigate)
The whole Colorlight DLL stack assumes a sender-card/IP topology; we talk to the
receiver raw-L2 directly, so every *live* DLL/Wine path is walled. BUT running the
DLL's serializer **offline under Unicorn emulation** (pure computation, no NIC) is
fine and is the path. The DLL's **data_emu generator `fcn.100fbe20`** (= singleton
`vtable[0x54]`, CLTDevice.dll base `0x10000000`) builds the filled VHDL from a
`.rdata`-embedded template + `sprintf("%.2X", byte)` and writes it ONCE to an
ofstream — so capturing that single `WriteFile` gives the byte-exact DISPLAY frames.

Wire frame (Ethernet, no preamble): `dst=11:22:33:44:55:66`, `src=22:22:33:44:55:66`,
`byte12=CMD`, `byte13-14=serial(u16 BE)`, `byte15=subframe`, `byte16+=payload`,
trailing additive-8 checksum (`test_crc`). Section CMD bytes (byte12): `0x02`
cardarea, `0x03` route, `0x76` gamma, `0x18` scan, `0x05` basic, `0x10` void, `0x01`
switch, `0xFF` init, `0x55` pixels.

## What Session 8 SOLVED (don't re-derive)
The emulated **file open now genuinely succeeds** — real `CreateFileW` fires and the
filebuf is fully built. Fixes already in `re/emu/gen_capture2.py`:
- **CRT stdio/lowio init:** seed `__piob`@`0x1028b900` (64-slot FILE* array),
  `_nstream`@`0x1028b904`=64, `__pioinfo[0]`@`0x10289f60` (ptr to 32× 0x40-byte
  ioinfo; osfhnd at +0, osfile flag at +4). Without these `_getstream` returned
  NULL (EMFILE) before CreateFileW.
- **CreateFile2 gate:** hook `0x101df935` → return 0, so the UCRT CreateFile wrapper
  (`0x101fabd0`) uses legacy `CreateFileW` instead of `GetProcAddress("CreateFile2")`
  (which our shim can't resolve → it returned INVALID_HANDLE_VALUE).
- The old gate je→jmp patches are OFF (behind `--force-gates`); not needed now.

## THE remaining blocker — set ONE app-level global, then capture
The generator null-derefs at `0x100c67d0` **even with a perfectly-open file** — it
is NOT a stream problem. Section-builder `0x100c9780` branches on an app-level mode
global `[0x1028a530]` (setter `0x101028b0`; valid values `0xd`/`0x19`) that headless
init leaves **0**, so it takes a bad path that virtual-calls through a null
sub-object pointer `[D+8]` (D = the display/codec struct).

`[0x1028a530]` is a GUI setting, NOT from the `.rcvp` — so we must set it ourselves.
**`InitFromFile` is a dead end** (converges on the same deserialize+build the
shortcut uses, and its ifstream open fails separately) — use the **shortcut** init.

## YOUR TASK
1. In `re/emu/gen_capture2.py`, just before the generator call
   (`call(0x100fbe20, [bigDataObj], ...)`), add:
   ```python
   uc.mem_write(0x1028a530, struct.pack("<I", 0xd))   # app "send/data mode"; try 0x19 too
   ```
   Run `cd re/emu && python3 gen_capture2.py --shortcut` (~2 min).
2. If it still faults on a *different* uninitialized mode-dependent global, set that
   one too (same pattern); iterate. If it completes, the `WriteFile` shim captures
   the VHDL to `re/emu/data_emu.vhd` (per-handle bytes are in `OUTWRITES`; the
   harness already picks the biggest output handle and dumps it).
3. Decide `0xd` vs `0x19` correctly: capture both, compare the VHDL against the panel
   config (12× 64×64, 32-scan from the `.rcvp` filename), or inspect what
   `0x100c9780` does differently for each.
4. Parse the VHDL (`elsif x = N then P0_RXD <= X"HH";` grouped by `y`-section) into
   per-section frames; rebuild each L2 frame (dst/src/CMD/serial/subframe/payload +
   additive-8 checksum). Send section-by-section over `enx9c69d388d76e` (panel
   powered, user watching); iterate on the `0x0805` reply's config fields going
   non-zero. Reuse the send/recv from `detect_5a75e.py`.

## Key addresses (CLTDevice.dll base 0x10000000)
- Generator `fcn.100fbe20`; stream gates `0x100fc003`/`0x100fc11c` (return -2/-3).
- Null-deref `0x100c67d0`, called from `0x100c9c2d` in section-builder `0x100c9780`.
- Mode global `[0x1028a530]`, setter `0x101028b0` (valid 0xd/0x19).
- Open chain: `ofstream::open 0x1002b780 → filebuf::open 0x101d6ff1 → _Fiopen(wide)
  0x101da864 → _getstream 0x101e83ab / _wopenfile 0x101ec14c → open-core 0x101fac58
  → _alloc_osfhnd 0x101fa775 → wrapper 0x101fabd0 → CreateFileW`.
- CRT globals: `__piob 0x1028b900`, `_nstream 0x1028b904`, `__pioinfo 0x10289f60`,
  CreateFile2 gate `0x101df935`.
- Init (shortcut): deserialize `0x100945f0`, display-build `0x101a8370`.
- InitFromFile (DEAD END): export `0x100e5470` → loader `0x101a5880` → ifstream-load
  `0x10090a80` → ifstream ctor/open `0x100a17d0` (fails before CreateFileW).

## Hard constraints (do not violate)
- **No Windows; no networked Wine.** Offline Unicorn emulation of DLL *computation*
  is OK (that's this task). No GUI on `DISPLAY=:0` (crashes VSCode — see memory
  `vscode-crash-cause`). Render any GUI to Xvfb `:99` only; we shouldn't need one.
- **Panel NIC = `enx9c69d388d76e`** (ASIX). Built-in `enp4s0` is dead; never use it.
- **Never unplug the USB WiFi dongle** (internet + your link to the user).
- **No JTAG/FTDI/Pico** available (rules out the gateware-flash Plan B for now).
- Root for raw sockets: `.env` has `SUDO_PASS`. Use without printing it, and NOT via
  a heredoc on the same command (write the script to a file first):
  ```bash
  set +H; set -a; . /home/muse/Desktop/LED/.env; set +a
  printf '%s\n' "$SUDO_PASS" | sudo -S -p '' python3 /path/to/script.py ...
  ```
- **Don't over-spawn subagents** (user preference); do the RE directly.
- Be honest about uncertainty. Keep `OPTION-F-PROGRESS.md` + memory updated.

## Quick commands
```bash
cat /sys/class/net/enx9c69d388d76e/carrier            # want 1
sudo python3 detect_5a75e.py enx9c69d388d76e          # CARD FOUND 0x0805, fw 6.0
cd re/emu && python3 gen_capture2.py --shortcut       # the generator-capture harness (~2 min)
# disassemble (CLTDevice base 0x10000000):
r2 -2 -q -e scr.color=0 -c 's 0x100c9780; pd 200' re/dll/CLTDevice.dll | less   # section-builder
r2 -2 -q -e scr.color=0 -c 's 0x100fbe20; pd 200' re/dll/CLTDevice.dll | less   # the generator
```
Tooling installed: `python3-unicorn` (2.0.1), `python3-capstone`, `pefile`, `radare2`.
Remind the user to `rm /home/muse/Desktop/LED/.env` when the project is done.
