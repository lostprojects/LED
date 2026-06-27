# LED Bar Menu — Setup Notes

Building a digital menu for a bar from **12× 64×64 RGB LED panels** driven by a
**Colorlight 5A-75E** receiving card, from a **Mac mini running Linux Mint 22.3**.

Status: bringing up **one** test panel first, then scaling to 12.

> **Note (2026-06-25):** This document covers **Path B (flash the open FPGA
> gateware via JTAG)**, which is now the **FALLBACK**. The primary plan is **Plan
> A — configure the stock card by running LEDVISION under Wine** (no JTAG, no
> hardware). See [`LED-PLAN.md`](LED-PLAN.md). Use this doc only if Plan A fails
> and a JTAG programmer (spare Pico/Blue Pill/FT232) is available.

Last updated: 2026-06-23 (Path-B notes); superseded as primary 2026-06-25

---

## 1. How this works (the big picture)

The **5A-75E is a _receiving_ card**, not a sender. Normally it sits between a
sending card / video processor and the panels, speaking a custom raw Layer‑2
Ethernet protocol over plain Cat5/6. We're skipping the sending card entirely.

Data path:

```
Linux (enp4s0) ──Cat5/6──> 5A-75E ──HUB75 ribbon cables──> 64×64 panels
```

The 5A-75E is secretly a **Lattice ECP5 FPGA** board, so instead of using
Colorlight's Windows-only configuration tool (LEDVISION), we **replace its
firmware with open FPGA gateware** that turns it into an **Art‑Net controller**.
After that, everything is configured and driven from Linux — no Windows, ever.

---

## 2. Decisions made

| Question | Answer |
|---|---|
| Card already configured? | **No — brand new** |
| Windows available? | **No — Linux only** |
| Panel driver chip | **Unknown** (need to read it off the panel) |
| Chosen approach | **Path B: flash open FPGA gateware (Art‑Net)** |

### Why Path B
- It is the only path that removes the Windows/LEDVISION dependency completely.
- Result is a clean, permanent, fully Linux‑native Art‑Net controller — a good
  foundation for a 12‑panel wall.
- Cost: a ~$5 JTAG programmer + a one‑time (recoverable) flash.

### Path A (rejected, for reference)
Keep the stock firmware and stream raw L2 Ethernet
([kostaman/LED_Matrix-1](https://github.com/kostaman/LED_Matrix-1)). The streaming
works on Linux, but **panel configuration still requires LEDVISION on Windows** —
a dealbreaker for a Linux‑only, brand‑new card.

---

## 3. The gateware we're using

Repo: **[jimbobelectronics123/colorlight_5a-75e_artnet](https://github.com/jimbobelectronics123/colorlight_5a-75e_artnet)**
(built on the [q3k/chubby75](https://github.com/q3k/chubby75/blob/master/5a-75e/README.md)
reverse‑engineering effort).

Cloned locally to: `./colorlight_5a-75e_artnet/`

What it gives us:
- **12 concurrent HUB75 ports** (J1–J12)
- Runtime config (panel type, offsets, scan limits) over **Art‑Net Universe 666**
- Supports **64×64**, stacked 32×64 pairs, 32×64, 32×32
- 5‑bit color depth (32,768 colors)
- Watchdog auto‑blanks panels if the Art‑Net stream stops
- Ships a **prebuilt `top.bit`** → no need to build from source to get started
- Helper scripts use **only the Python standard library** (nothing to install):
  - `config_panel.py` — set IP + per‑port panel layout
  - `send_artnet.py` — push pixels / test patterns

Target board per the repo: **5A‑75E v8.2**, ECP5 **LFE5U‑25F**, **W25Q32JV** SPI flash.

---

## 4. ✅ Driver‑chip risk — RESOLVED (this panel is "flash‑and‑go")

The panel's chips were identified:

| Role | Chip | Verdict |
|---|---|---|
| Column / data driver | **DP5125D** | **Standard** driver — **no** FM6126A‑style power‑on init needed ✅ |
| Row / scan driver | **SM5166PS** | **Standard "138‑type" decoder**, driven directly by A–E address lines (1/32 scan) ✅ |

Why this is the good case: the gateware's `hub75_driver.v` outputs
`{e,d,c,b,a} <= row` (row 0–31) and a plain clock/latch/OE data stream — exactly
what a DP5125D + SM5166 (decoder) 64×64 1/32 panel expects. So the **prebuilt
`top.bit` should drive this panel directly with `panel_type = 0` (64×64)** — no
Verilog patch, no rebuild.

### What would have been the hard case (for reference)
- A **FM6126A / FM6124** column driver → needs a register‑init sequence the
  gateware lacks → would need a Verilog patch + rebuild.
- A **shift‑register‑type row driver** (DP32020A, DP3246/SM5368, SM5266P) → needs
  serial row clocking instead of A–E decode → also needs gateware changes.
This panel has **neither** — it's the plain, well‑supported combination.

---

## 5. Hardware checklist

- [ ] **JTAG programmer** — a [DirtyJTAG](https://github.com/jeanthom/DirtyJTAG)
      probe: a **Raspberry Pi Pico (RP2040, ~$4)** or STM32 **"Blue Pill"**,
      flashed with DirtyJTAG firmware.
- [ ] **4 jumper wires + ground** from the programmer to the 5A‑75E's
      **unpopulated 4‑pin JTAG header** (TCK / TMS / TDI / TDO) + GND.
- [ ] **5V power** for the panel *and* the 5A‑75E (separate supply / from the panel).
- [ ] **Cat5/6** from Mac mini Ethernet jack → 5A‑75E **input** RJ45.

---

## 6. Environment facts (Mac mini)

| Item | Value |
|---|---|
| OS | Linux Mint 22.3 (Ubuntu 24.04 base), x86_64 |
| Host model | **Macmini8,1** (2018, Apple T2 chip) |
| Built-in NIC `enp4s0` | Broadcom BCM57766 / `tg3` — **DEAD under Linux, do not use.** Never links (carrier 0) vs card, fresh cable, or switch; no PHY reaction to cable; `tg3: No firmware running`. Likely T2-locked NVRAM → PHY firmware never loads. |
| Wired NIC (for panels) | **USB 3.0 Gigabit adapter — TO BUY** (Realtek RTL8153/`r8152` preferred). Will appear as `enx<mac>`; use that iface in all scripts. |
| Internet | WiFi `wlx7419f816ce33` (192.168.1.64) USB dongle — keep panels off this |
| `git` | NOT installed (repo fetched via tarball) |
| `openFPGALoader` | NOT installed (apt candidate 0.12.0) |
| `python3`, `gcc` | present |
| sudo | needs a password (run installs interactively) |

---

## 7. Step‑by‑step plan

### Phase 0 — Identify & prep (current)
1. **ID the driver chip** — DONE: DP5125D + SM5166PS, standard → flash‑and‑go.
2. **Verify the card talks in STOCK state** (before any flashing):
   - Power the panel + 5A‑75E; Cat5/6 from Mac mini → card **input** RJ45.
   - Confirm link: `cat /sys/class/net/enp4s0/carrier` → want `1`.
   - Run the detector (raw sockets need root):
     ```bash
     sudo python3 detect_5a75e.py enp4s0
     ```
   - Expect "CARD FOUND — 0x0805" with firmware + configured cabinet size.
     This proves two‑way comms over the stock Colorlight protocol.
3. **Photo the 5A‑75E** (both sides) — confirm revision, locate JTAG header pinout.
4. **Get a JTAG programmer** (Pico or Blue Pill) and flash DirtyJTAG onto it.
5. Install the flashing tool:
   ```bash
   sudo apt update && sudo apt install -y openfpgaloader
   ```

Protocol used by `detect_5a75e.py` (stock Colorlight, Layer‑2, no IP):
- `0x0700` = detection query (we broadcast it); `0x0805` = card's reply
  (firmware, cabinet W×H, uptime, packet count, receiver id).
- card MAC `11:22:33:44:55:66`, sender MAC `22:22:33:44:55:66`.

### Phase 1 — Flash the gateware
5. Wire the programmer to the 5A‑75E JTAG header (board powered).
6. Confirm the ECP5 is detected:
   ```bash
   openFPGALoader -c dirtyJtag --detect
   ```
7. Flash the prebuilt bitstream to SPI flash:
   ```bash
   cd colorlight_5a-75e_artnet
   openFPGALoader -c dirtyJtag -f --unprotect-flash top.bit
   ```
8. Power‑cycle the card. Status LED should heartbeat‑blink. Default IP `10.10.10.10`.

### Phase 2 — Bring up ONE panel
9. Cat5/6 from Mac mini → card input. Give `enp4s0` an IP on the card's subnet:
   ```bash
   sudo ip addr add 10.10.10.1/24 dev enp4s0 && sudo ip link set enp4s0 up
   ```
10. Configure J1 as a 64×64 panel (Universe 666) and send a test pattern:
    ```bash
    python3 config_panel.py    # set IP + J1 panel_type=0 (64x64)
    python3 send_artnet.py     # test pattern
    ```
11. If dark/garbled → revisit the **driver‑chip** question (FM6126A patch).

### Phase 3 — Scale to 12 panels
12. Map each panel to a J‑port and stream the matching universes (see §8).
13. Decide physical arrangement (e.g. 4 wide × 3 tall = 256×192) and build a
    renderer that draws the menu and emits Art‑Net per port.

---

## 8. Art‑Net reference (from the gateware README)

**Default IP:** `10.10.10.10`

**Config — send to Universe 666 (0‑indexed):**
- Channels 1–4 = IP address (e.g. `192.168.1.100`).
  - DHCP: send `0.0.5.2` (status LED double‑blinks).
- Then 3 channels per J‑port starting at Ch 5:
  - `panel_type` (0 = 64×64, 1 = stacked/chained 32×64, 2 = std 32×64/32×32, 3 = chained 32×32)
  - `max_active_y` (scanline limit, e.g. 32 or 16)
  - `start_active_x` (column offset, e.g. 0/32/64/96)
  - J1 = Ch 5–7, J2 = Ch 8–10, … J12 = Ch 38–40.

**Pixel universe mapping (32 universes per port, consecutive):**

| Port | Universes | Port | Universes |
|---|---|---|---|
| J1 | 0–31 | J7 | 192–223 |
| J2 | 32–63 | J8 | 224–255 |
| J3 | 64–95 | J9 | 256–287 |
| J4 | 96–127 | J10 | 288–319 |
| J5 | 128–159 | J11 | 320–351 |
| J6 | 160–191 | J12 | 352–383 |

**Reset to default IP:** hold onboard button (site R7) 10s; LED blinks ~7.5 Hz then
goes solid; IP reverts to `10.10.10.10`.

---

## 9. Open questions / TODO
- [x] Driver chip identity → **DP5125D (col) + SM5166PS (row), both standard, flash‑and‑go**
- [ ] 5A‑75E board revision + JTAG pinout (from photo)
- [ ] Which JTAG programmer (Pico vs Blue Pill) — do we own one?
- [ ] Final physical layout of the 12 panels (grid shape, orientation)
- [ ] Power budget: 12× 64×64 panels can draw a lot at 5V — size the PSU(s)
- [ ] Menu renderer: what generates the content (static images? live text?)
```

---

## 10. Key links
- Gateware: https://github.com/jimbobelectronics123/colorlight_5a-75e_artnet
- Hardware RE (chubby75): https://github.com/q3k/chubby75/blob/master/5a-75e/README.md
- DirtyJTAG: https://github.com/jeanthom/DirtyJTAG
- openFPGALoader: https://github.com/trabucayrog/openFPGALoader
- Protocol RE (Harald Kubota): https://hkubota.wordpress.com/2022/01/31/winter-project-colorlight-5a-75b-protocol/
- Alt path (stock firmware sender): https://github.com/kostaman/LED_Matrix-1
