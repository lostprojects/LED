# Zero-Config Plug-and-Play Art-Net HUB75(E) Controller

This project implements an Art-Net controller on the **Colorlight 5A-75E v8.2** board (Lattice ECP5 LFE5U-25F). It defaults to zero-configuration plug-and-play for standard panels, and supports dynamic runtime configuration of layouts, offsets, and scanline limits via a dedicated configuration universe (Universe 666).

## Features
	
	*   **12 Concurrent Ports**: Drives up to 12 active HUB75(E) output ports (J1 - J12) simultaneously.
	*   **Runtime Configuration**: Adjust panel types, offsets, and active scanline limits on the fly using DMX Universe 666.
	*   **Mixed Sizes Supported**: Supports 64x64, stacked 32x64 pairs (behaving as a single logical 64x64 panel), standard 32x64, and standard 32x32 panels.
	*   **5-Bit Color Depth**: Memory-optimized BRAM implementation providing 32,768 colors.
	*   **Flicker-Free Watchdog**: Auto-blanks all panels within 0.5s if the Art-Net stream is interrupted.

---
## Default IP Address

	10.10.10.10 

## Configuration & Changing the IP Address
     
	To configure the controller at runtime, send an Art-Net packet to **UNIVERSE 666** (0-indexed). The first 4 channels of the payload set the IP address, and subsequent 3-channel blocks configure the panel layouts for each J-port.
	
	### IP Configuration (Channels 1–4):
	*   **Static IP**: Send `Ch1.Ch2.Ch3.Ch4` (e.g. `192.168.1.100`).
	*   **DHCP Mode**: Send `0.0.5.2` (or any byte sequence representing 42, such as `0.0.0.42`). The status LED will double-blink (`blink-blink-pause`) to confirm DHCP request mode.

	### J-Port Configuration Map (3 channels per port starting at Ch 5):
	*   **J1**:
	    *   `Ch 5`: `panel_type` (0 = 64x64, 1 = Stacked/Chained 32x64, 2 = Standard 32x64/32x32, 3 = Chained 32x32)
	    *   `Ch 6`: `max_active_y` (height scan scanline limit, e.g., 32 or 16)
	    *   `Ch 7`: `start_active_x` (column coordinate offset, e.g., 0, 32, 64, 96)
	*   **J2** (Channels 8–10), **J3** (Channels 11–13), and so on up to **J12** (Channels 38–40).

## Art-Net Universe Layout Mapping (32 Universes Per Port, Consecutive)

	*   **J1** - UNIVERSE `0-31`
	*   **J2** - UNIVERSE `32-63`
	*   **J3** - UNIVERSE `64-95`
	*   **J4** - UNIVERSE `96-127`
	*   **J5** - UNIVERSE `128-159`
	*   **J6** - UNIVERSE `160-191`
	*   **J7** - UNIVERSE `192-223`
	*   **J8** - UNIVERSE `224-255`
	*   **J9** - UNIVERSE `256-287`
	*   **J10** - UNIVERSE `288-319`
	*   **J11** - UNIVERSE `320-351`
	*   **J12** - UNIVERSE `352-383`

	*(Note: Because the mapping is consecutive with no gaps, you stream all universes for a port consecutively starting from the port's base universe).*
	For 2 32x32 panels daisy-chained together (4 rows/universe) (1/16 scan): Set your output to map universes 0–15 consecutively.
	For 3 32x32 panels daisy-chained together (4 rows/universe) (1/16 scan): Set your output to map universes 0–23 consecutively.
	For 4 32x32 panels daisy-chained together (4 rows/universe) (1/16 scan): Set your output to map universes 0–31 consecutively.
---

## Physical Reset Button (Revert to 10.10.10.10)
	
	Press & Hold: Press and hold the onboard user button (button SITE R7).
	Visual Blinking Feedback: As soon as the button is pressed, the status LED will override its normal heartbeat and start blinking rapidly (~7.5 Hz) to show that the 10-second timer is counting down.
	Reset Triggered: Keep holding the button for 10 seconds. Once the 10-second threshold is met, the status LED will turn solid ON.
	IP Restored: The board's IP address instantly reverts back to 10.10.10.10.
	Release Button: Once you release the button, the LED reverts to its normal heartbeat blink.


## How to Compile & Flash
	
	### 1. Compilation
	The project is compiled using the open-source Yosys/nextpnr toolchain. You can run the build script:
	```bash
	./build.sh
	```
	This generates the compressed `top.bit` bitstream file.

	### 2. Flashing over JTAG (using DirtyJTAG)
	To permanently program the bitstream to the board's Winbond SPI flash over JTAG using a [DirtyJTAG](https://github.com/jeanthom/DirtyJTAG) programmer:
	```bash
	openFPGALoader -c dirtyJtag -f --unprotect-flash top.bit
	```

## Sources & References

	This implementation relies on the following resources:
		*   **Ethernet MAC/PHY Core**: Generated using [LiteEth](https://github.com/enjoy-digital/liteeth) by Florent Kermarrec / Enjoy-Digital.
		*   **JTAG Adapter Firmware**: [DirtyJTAG](https://github.com/jeanthom/DirtyJTAG) by Jean Thomas / jeanthom (turns Blue Pill or RP2040 into a JTAG probe).
		*   **Toolchain**: Compiled using the open-source FPGA toolchain [Yosys](https://github.com/YosysHQ/yosys) (synthesis) and [nextpnr-ecp5](https://github.com/YosysHQ/nextpnr) (place-and-route).
		*   **Flashing Utility**: Programmed over JTAG using [openFPGALoader](https://github.com/trabucayrog/openFPGALoader).
		*   **AI Pair Programmer**: Co-designed, implemented, and optimized by **Antigravity** (Google DeepMind's AI coding assistant).
			Thank You All!