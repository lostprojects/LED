import socket
import time
import math
import argparse

# Colorlight board configuration
DEFAULT_IP = "10.10.10.10"
DEFAULT_PORT = 6454

def make_artnet_packet(universe, dmx_data):
    # Art-Net header
    header = bytearray(18)
    header[0:8] = b"Art-Net\x00"     # ID
    header[8:10] = b"\x00\x50"       # OpCode: OpDmx (0x5000, little endian -> 00 50)
    header[10:12] = b"\x00\x0e"      # Protocol Version 14
    header[12] = 0                   # Sequence (0 to disable)
    header[13] = 0                   # Physical port
    header[14] = universe & 0xFF     # Universe LSB
    header[15] = (universe >> 8) & 0x7F # Universe MSB
    
    # Length of DMX data (must be even, between 2 and 512)
    length = len(dmx_data)
    header[16] = (length >> 8) & 0xFF
    header[17] = length & 0xFF
    
    return header + dmx_data

def main():
    parser = argparse.ArgumentParser(description="Send Art-Net test patterns to Colorlight board")
    parser.add_argument("--ip", default=DEFAULT_IP, help=f"Board IP address (default: {DEFAULT_IP})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Art-Net port (default: {DEFAULT_PORT})")
    parser.add_argument("--panels", type=int, default=12, help="Number of logical panels/ports to drive (default: 12)")
    parser.add_argument("--mode", choices=["unified", "independent"], default="unified", 
                        help="Display mode: 'unified' 3x3 layout or 'independent' per-panel patterns (default: unified)")
    parser.add_argument("--fps", type=float, default=30.0, help="Target frames per second (default: 30)")
    
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Sending Art-Net test patterns ({args.mode} mode) to {args.ip}:{args.port}...")
    print(f"Driving {args.panels} logical panels (J1 to J{args.panels}) -> {args.panels * 32} universes total.")
    print("Press Ctrl+C to stop.")

    universes_per_panel = 32
    total_universes = args.panels * universes_per_panel
    pixels_per_universe = 128 # 384 DMX channels

    t = 0
    frame_interval = 1.0 / args.fps
    
    try:
        while True:
            start_time = time.time()
            t += 0.05
            
            for u in range(total_universes):
                panel = u // universes_per_panel
                local_u = u % universes_per_panel
                
                dmx_data = bytearray(384) # 128 pixels * 3 channels
                
                # Determine panel position in 3x3 grid for unified mode
                if args.mode == "unified":
                    panel_col = panel % 3
                    panel_row = panel // 3
                
                # Under the 32-universe system, there are no gaps
                coord_local_u = local_u
                
                for p in range(pixels_per_universe):
                    global_pixel_idx = coord_local_u * pixels_per_universe + p
                    if global_pixel_idx >= 4096:
                        break
                    
                    if panel < 7:
                        # Standard 64x64 grid
                        x = global_pixel_idx % 64
                        y = global_pixel_idx // 64
                    elif panel == 7:
                        # Stacked/Chained 32x64 (horizontal 128x32 display)
                        panel_idx = global_pixel_idx // 2048
                        x = (1 - panel_idx) * 64 + (global_pixel_idx % 64)
                        y = (global_pixel_idx % 2048) // 64
                    else:
                        # Chained 32x32 grid (up to 4 panels)
                        panel_idx = global_pixel_idx // 1024
                        x = (3 - panel_idx) * 32 + (global_pixel_idx % 32)
                        y = (global_pixel_idx % 1024) // 32
                    
                    if args.mode == "unified":
                        # Map to a global 192x192 grid
                        gx = panel_col * 64 + x
                        gy = panel_row * 64 + y
                        
                        # Generate a beautiful unified plasma wave pattern
                        r = int(127.5 + 127.5 * math.sin(gx / 16.0 + t))
                        g = int(127.5 + 127.5 * math.sin(gy / 16.0 - t))
                        b = int(127.5 + 127.5 * math.sin((gx + gy) / 32.0 + t / 2.0))
                    else:
                        # Independent per-panel plasma wave pattern
                        r = int(127.5 + 127.5 * math.sin(x / 8.0 + t + panel))
                        g = int(127.5 + 127.5 * math.sin(y / 8.0 - t - panel))
                        b = int(127.5 + 127.5 * math.sin((x + y) / 16.0 + t / 2.0))
                    
                    # Map colors to DMX data
                    idx = p * 3
                    dmx_data[idx]   = r
                    dmx_data[idx+1] = g
                    dmx_data[idx+2] = b
                
                packet = make_artnet_packet(u, dmx_data)
                sock.sendto(packet, (args.ip, args.port))
                
            # Throttle frame rate accurately
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_interval - elapsed)
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\nStopped sending Art-Net packets.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
