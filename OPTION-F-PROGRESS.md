# Option F progress — the data_emu generator path

Goal of Option F: get the **byte-exact DISPLAY wire frames** (the `data_emu` format)
and replay them from pure Python to configure + light the panel. We let the DLL
compute them for us by running its own generator offline under Unicorn emulation.

Harness: **`re/emu/gen_capture2.py`** (run `python3 gen_capture2.py --shortcut`).
CLTDevice.dll base = `0x10000000`. Statically-linked MSVC/UCRT CRT.

---

## Wire format (ground truth, from the DLL itself)

`data_emu.txt` is a TEMPLATE; the generator `fcn.100fbe20` (= singleton
`vtable[0x54]`) fills it. **The VHDL template skeleton is embedded in `.rdata`**
(around `0x10246dc2`, lines `elsif x = N then P0_RXD <= X"HH";`), so the generator
does NOT read a template file — it builds the filled VHDL string from embedded
fragments + `sprintf("%.2X", byte)` and writes it ONCE to an `ofstream`
(`data_emu.txt`/`.vhd`). So capturing that single `WriteFile` = the byte-exact VHDL.

Frame layout (Ethernet, no preamble): `dst=11:22:33:44:55:66`,
`src=22:22:33:44:55:66`, `byte12=CMD`, `byte13-14=serial(u16 BE)`, `byte15=subframe`,
`byte16+=payload`, trailing additive-8 checksum (`test_crc`). Section CMD bytes
(byte12): `0x02` cardarea, `0x03` route, `0x76` gamma, `0x18` scan, `0x05` basic,
`0x10` void, `0x01` switch, `0xFF` init, `0x55` pixels.

---

## SESSION 9 (2026-06-27): GENERATOR RUNS TO COMPLETION — all sections captured

**The real blocker was NOT the mode global — it was an off-by-0x10 on the generator's
arg0.** Two fixes, both in `gen_capture2.py`, now make `fcn.100fbe20` build the full
filled VHDL:

1. **arg0 must be `codec-0x10`, not `codec`.** The generator does
   `lea esi,[arg0+0x10]` (0x100fbe74) and treats `arg0+0x10` as the display struct
   `D`. We were passing `arg0=[crop+8]=codec` (0x40001990), so `D=codec+0x10` =
   garbage (W=0,H=7,scan=0 → `idiv` by 0). Passing `arg0=codec-0x10` makes
   `D=codec` = the real display struct: **W@+0x3c=64, H@+0x3e=32, scan@+0x85=32**.
   Run flag: `--argoff -0x10`. (codec=`[crop+8]`, crop=`[singleton getter]`.)
2. **mode global `[0x1028a530]`** (`--mode 0xd`, setter 0x101028b0) selects the
   good path 0x100c97c1 vs the default 0x100c9b71 in section-builder 0x100c9780.
   BUT the good path has a 2nd gate `cmp byte[D+0xd650],0; je 0x100c9b71` and that
   byte is 0 (it's bit16 of a config-flags dword that deserialized as 0), so it
   falls to 0x100c9b71 anyway. **With the correct D, that "bad" path completes fine
   and produces all sections** — so the off-by-0x10 was the whole bug; mode=0xd is
   currently cosmetic. (Open Q: is bit16=0 correct for this config, i.e. is the
   0x100c9b71 path the byte-exact one? Validate against the live card.)

**Run:** `python3 gen_capture2.py --shortcut --mode 0xd --argoff -0x10` → builds
36273 string-append ops across **21 section blobs** (dumped to `gen_dests.json` +
the biggest to `data_emu_filled.txt`).

### What the generator emits (and what it does NOT)
- The full data_emu.txt = an external **template** (`re/data_emu.txt`, 12801 B, with
  `#-CARDAREA-#`/`#-BASICROUTE-#`/`#-SCANSCHEDULE-#`/… placeholders) whose
  placeholders get replaced. **The template header/boilerplate is NOT in the DLL**
  (`auto generated sim file`, `library ieee`, `P0_RXC`, `frame_row_buff`, `Behavioral`
  are all absent from CLTDevice.dll) and our headless run never loads it, so the
  generator only emits the **section data** (the placeholder *replacements*), not the
  assembled file. That's fine — **the wire frames live entirely in the section
  `P0_RXD` data**, not the VHDL boilerplate.
- 21 sections (gen_dests.json), in generation order, include gamma/HDR/HLG tables,
  void/anti-void line info, gamma calibration, anti pixel sequence, data remapping,
  basic parameters (y=162), T/R8 AntiRouteTables, etc. The small blobs (call#2 len5156,
  call#8732/8989 len11250) likely hold cardarea/route/scan/switch config.

### The end-crash is cosmetic
After building everything the run faults with `EIP=0xbb40e64e` (= the /GS cookie):
the ofstream filebuf is fully buffered and only flushes at `close()`; the close-flush
crashes in CRT locale/codecvt conversion (blocks 0x101e23xx/0x101e92xx) of the big
buffer, so **nothing reaches the WriteFile shim** (handle 0x1001 got 0 bytes). The
content is the section blobs (already captured via the append hooks). A heap scan for
the header finds nothing because the template was never loaded.

### NEXT
- Map the 21 section blobs → template placeholders (order ≈ first_call order) and/or
  parse each blob's `elsif x = N then P0_RXD <= X"HH";` directly into the per-section
  byte stream → L2 frames (dst/src/CMD/serial/subframe + additive-8 checksum).
- Send the config sections (cardarea/route/scan/basic/switch) to the card over
  `enx9c69d388d76e`, watch the 0x0805 reply's config fields. Validate which mode/path
  is byte-exact against the live card.

---

## SESSION 8 (2026-06-26): file I/O in the emulator is now SOLVED

The Session-7 blocker ("the ofstream open fails") is **fixed**. The open now
genuinely succeeds — `_Fiopen-wide → OK FILE*`, real `CreateFileW` fires, and the
filebuf is fully built. Two precise root causes, both fixed in `gen_capture2.py`:

1. **CRT stdio/lowio tables were uninitialized** (we bypass `_DllMainCRTStartup`).
   `_getstream` (`0x101e83ab`) returned NULL (EMFILE) because `_nstream`
   (`0x1028b904`) was 0 and `__piob` (`0x1028b900`) was NULL. Fix: allocate a 64-slot
   `__piob` FILE* array, set `_nstream=64`, and seed `__pioinfo[0]` (`0x10289f60`,
   array of ptrs to 32× 0x40-byte ioinfo structs; osfhnd at +0, osfile flag at +4).

2. **The UCRT CreateFile wrapper preferred `CreateFile2`.** Wrapper `0x101fabd0`
   asks the feature-gate `0x101df935` "is CreateFile2 available?"; under emulation it
   answered yes, so the wrapper did `GetProcAddress("CreateFile2")` → our shim
   returns 0 → wrapper returns `INVALID_HANDLE_VALUE`. Fix: **hook `0x101df935` to
   return 0** → wrapper uses the legacy `CreateFileW` path (our shim handles it).

The real ofstream-open chain (for reference / re-tracing):
`ofstream::open 0x1002b780 → filebuf::open 0x101d6ff1 (→0x101d6f46) → 0x101d7017 →
_Fiopen(wide) 0x101da864 → {_getstream 0x101e83ab, _wopenfile 0x101ec14c →
open-core 0x101fac58 (via 0x101fb474) → _alloc_osfhnd 0x101fa775 → wrapper
0x101fabd0 → CreateFileW}`. (The narrow `_Fiopen` 0x101d8a9e / `_wopenfile`
0x101e84ca exist too but this char-ofstream uses the wide variant.)

The Session-7 gate je→jmp patches (`0x100fc003`/`0x100fc11c`) are no longer needed
and are OFF by default (kept behind `--force-gates`); the gates pass on their own
now that the stream is genuinely good.

## THE REMAINING BLOCKER (the actual one): an uninitialized APP-LEVEL mode global

With file I/O fixed, the generator runs further but **null-derefs at `0x100c67d0`**
(this was NOT a stream problem — it persists with a perfectly-open file). Diagnosis:

- The generator's section-builder **`0x100c9780`** branches on a global
  **`[0x1028a530]`** (its setter is the 1-line `0x101028b0`: `[0x1028a530]=arg`).
  Valid values are **`0xd` (13)** or **`0x19` (25)**; in headless init it stays **0**.
- `[0x1028a530]` is an **application/GUI setting** (a "send/data mode"), NOT derived
  from the `.rcvp` — so neither the shortcut NOR `InitFromFile` sets it.
- With mode 0, `0x100c9780` takes a default branch (`0x100c9b71` → `0x100c9c0e` →
  `0x100c9c2d`) that calls `0x100c67d0`, which does a virtual call through a null
  sub-object pointer `[D+8]` (D = `[this]` = the display/codec struct) → fault.

## `InitFromFile` is a DEAD END (don't reopen)

`_CLTReceiverRcvParamInitFromFile@4` (`0x100e5470`) → `crop.vtable[0x48]` loader
(`0x101a5880`) → ifstream-load (`0x10090a80`). This **converges on the same
`0x100945f0` (deserialize) + `0x101a8370` (build display)** the shortcut already
calls — so it would NOT set `[0x1028a530]` either. Worse, its ifstream open
(`0x100a17d0`) fails before `CreateFileW` (stream bad → returns `0xe0830012`); the
ifstream path is a *separate*, deeper rabbit hole. The **shortcut init is strictly
better** and is the path: memory-deserialize `0x100945f0` + display-build
`0x101a8370` (both succeed: result `0`).

---

## NEXT STEP — pick the mode, capture the VHDL

**Immediate experiment (one ~2-min run):** with the shortcut init, set
`[0x1028a530] = 0xd` (try `0x19` too) just before calling the generator, e.g.:

```python
uc.mem_write(0x1028a530, struct.pack("<I", 0xd))   # app "send/data mode"
```

Then run `gen_capture2.py --shortcut`. Expected: `0x100c9780` takes the good path,
the generator builds the full VHDL std::string and writes it to the ofstream → the
**`WriteFile` shim captures the byte-exact VHDL** (dumped to `re/emu/data_emu.vhd`,
with per-handle capture already wired up as `OUTWRITES`). Watch for:
- a follow-on null/uninit on a different mode-dependent global (set those too), or
- success: a >4 KB VHDL with all sections → parse it.

To choose `0xd` vs `0x19` correctly, compare the two outputs against the panel
config, or inspect what `0x100c9780` does differently for each (both reach the good
path `0x100c97c1`; they likely select a data-grouping/scan variant).

**Then:** parse the captured VHDL (`elsif x = N then P0_RXD <= X"HH";` grouped by
`y`-section) into per-section frames; rebuild each L2 frame (dst/src/CMD/serial/
subframe/payload + additive-8 checksum); send section-by-section over
`enx9c69d388d76e` (panel powered, user watching) and iterate on the `0x0805` reply's
config fields going non-zero. Reuse the send/recv from `detect_5a75e.py`.

## Artifacts this session
- `re/emu/gen_capture2.py` — the working harness. Flags: `--shortcut` (use the
  shortcut init — DO THIS), `--force-gates` (restore the old je→jmp gate patches).
  Default (no flag) tries the dead-end `InitFromFile` route. The mode-global
  `mem_write(0x1028a530, ...)` is NOT yet in the file — add it (see NEXT STEP).
  `re/emu/gen_capture.py` is the Session-7 original (file-open still failing).
- This file + memory `[[colorlight-data-emu-generator]]`.
