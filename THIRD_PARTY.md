# Third-party software

Every part of this project that uses someone else's software is declared here.
The machine-readable summary lives in [`pyproject.toml`](pyproject.toml)
(`[project].dependencies` for pip packages, `[tool.thirdparty.*]` for the rest);
this file carries the detail, provenance, and licensing notes.

---

## 1. Python packages (pip-installable)

Declared in `pyproject.toml` → `[project].dependencies`. Install with:

```bash
pip install -e .        # or: pip install pefile unicorn
```

| Package | License | Used by | Purpose |
|---|---|---|---|
| [pefile](https://github.com/erocarrera/pefile) | MIT | `re/emu/*.py` | Parse the 32-bit PE (`CLTDevice.dll`) — sections, imports, IAT. |
| [Unicorn Engine](https://github.com/unicorn-engine/unicorn) | GPL-2.0 (Python bindings) | `re/emu/*.py` | Emulate the DLL's config serializer offline to capture wire frames. |

The other imports in the Python sources (`socket`, `struct`, `ctypes`, `json`, …)
are CPython standard library — no third party.

---

## 2. Proprietary binaries (NOT redistributed)

These are **Colorlight's** proprietary DLLs from the LEDVISION software. They are
**not committed** to this repo (see `.gitignore`) and must be supplied locally.

| File | Source | Role here |
|---|---|---|
| `re/dll/CLTDevice.dll` | Colorlight **LEDVISION** install | RE target — config serializer (`data_emu` generator). |
| `re/dll/CLTNic.dll` | Colorlight **LEDVISION** install | RE target — WinPcap/NIC send layer. |
| `re/dll/CommonClass.dll` | Colorlight **LEDVISION** install | RE target — shared helpers. |

**To obtain them:** install Colorlight LEDVISION (free, from Colorlight's website),
then copy the three DLLs from its install directory into `re/dll/`. They are used
only as inputs to static analysis and offline emulation — no proprietary code is
redistributed here.

---

## 3. Vendored open-source project

| Path | Upstream | Builds on | Notes |
|---|---|---|---|
| `colorlight_5a-75e_artnet/` | jimbobelectronics — *colorlight_5a-75e_artnet* | [q3k/chubby75](https://github.com/q3k/chubby75) | Art-Net HUB75 gateware for the 5A-75E (Lattice ECP5). This is the **Plan B** fallback (flash open gateware over JTAG). No upstream LICENSE file was bundled with the copy in this tree — confirm the upstream license before redistributing. |

That gateware itself depends on (does not vendor) the toolchain in §4.

---

## 4. System toolchain (install via your OS, not pip)

Invoked by build/RE steps; none are bundled.

| Tool | Used for | Project |
|---|---|---|
| Wine | Run the real LEDVISION/CLTNic against libpcap (reference route) | <https://winehq.org> |
| radare2 | Static RE of the DLLs (`re/cltdevice.r2proj`) | <https://rada.re> |
| LiteEth | Ethernet MAC/PHY core for the gateware | <https://github.com/enjoy-digital/liteeth> |
| Yosys | FPGA synthesis | <https://github.com/YosysHQ/yosys> |
| nextpnr-ecp5 | FPGA place-and-route | <https://github.com/YosysHQ/nextpnr> |
| openFPGALoader | Flash the bitstream over JTAG | <https://github.com/trabucayre/openFPGALoader> |
| DirtyJTAG | Blue Pill / RP2040 JTAG probe firmware | <https://github.com/jeanthom/DirtyJTAG> |
