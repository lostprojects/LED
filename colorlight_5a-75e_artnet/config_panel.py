#!/usr/bin/env python3
import sys
import socket
import argparse
import json

# UDP Destination Info
DEFAULT_IP = "192.168.1.200"
DEFAULT_PORT = 2000

# Panel Configuration Constants
PANEL_PRESETS = {
    "64x64": {
        "type": 0,
        "max_y": 32,
        "start_x": 64,
        "desc": "Standard 64x64 panel (1/32 scan)"
    },
    "stacked_32x64": {
        "type": 1,
        "max_y": 16,
        "start_x": 0,
        "desc": "Stacked 2x 32x64 panels daisy-chained (behaves as 64x64)"
    },
    "32x64": {
        "type": 2,
        "max_y": 16,
        "start_x": 64,
        "desc": "Standard 32x64 panel (1/16 scan)"
    },
    "32x32": {
        "type": 2,
        "max_y": 16,
        "start_x": 96,
        "desc": "Standard 32x32 panel (1/16 scan)"
    },
    "64x32": {
        "type": 2,
        "max_y": 16,
        "start_x": 64,
        "desc": "Standard 64x32 panel (1/16 scan)"
    }
}

def build_config_packet(layout):
    """
    Builds a 48-byte UDP packet for up to 16 logical drivers.
    Each driver consumes 3 bytes:
      Byte 0: phys_port (bits 3:0), panel_type (bits 5:4)
      Byte 1: max_active_y (bits 5:0)
      Byte 2: start_active_x (bits 7:0)
    """
    packet = bytearray(48)
    
    for i in range(16):
        # Default fallback config (logical i -> physical i, standard 64x64)
        phys_port = i
        panel_type = 0
        max_y = 32
        start_x = 64
        
        # Override with layout if specified
        if i < len(layout):
            entry = layout[i]
            if entry:
                phys_port = entry.get("phys_port", i)
                preset_name = entry.get("size", "64x64")
                
                if preset_name in PANEL_PRESETS:
                    preset = PANEL_PRESETS[preset_name]
                    panel_type = preset["type"]
                    max_y = preset["max_y"]
                    start_x = preset["start_x"]
                else:
                    panel_type = entry.get("type", 0)
                    max_y = entry.get("max_y", 32)
                    start_x = entry.get("start_x", 64)
        
        # Pack into 3 bytes
        byte0 = (phys_port & 0x0F) | ((panel_type & 0x03) << 4)
        byte1 = max_y & 0x3F
        byte2 = start_x & 0xFF
        
        packet[3*i + 0] = byte0
        packet[3*i + 1] = byte1
        packet[3*i + 2] = byte2
        
    return packet

def run_interactive():
    print("====================================================")
    print("   Colorlight HUB75 Interactive Layout Configurator ")
    print("====================================================\n")
    
    ip = input(f"Enter Colorlight IP Address [{DEFAULT_IP}]: ").strip()
    if not ip:
        ip = DEFAULT_IP
        
    print("\nSelect Active Mode:")
    print("  1) Mode A (8 active ports at 6-bit color depth)")
    print("  2) Mode B (16 active ports at 4-bit color depth)")
    mode_choice = input("Choice [1]: ").strip()
    
    num_ports = 16 if mode_choice == "2" else 8
    layout = [None] * num_ports
    
    presets_keys = list(PANEL_PRESETS.keys())
    
    for i in range(num_ports):
        print(f"\n--- Configure Logical Driver {i} ---")
        use_port = input(f"Enable Logical Driver {i}? (y/n) [y]: ").strip().lower()
        if use_port == 'n':
            continue
            
        # Select Physical J Port
        while True:
            phys_j = input(f"Map to physical output port J1-J16 [J{i+1}]: ").strip().upper()
            if not phys_j:
                phys_port = i
                break
            try:
                if phys_j.startswith("J"):
                    phys_port = int(phys_j[1:]) - 1
                else:
                    phys_port = int(phys_j) - 1
                if 0 <= phys_port <= 15:
                    break
                print("Invalid port number. Enter J1 to J16.")
            except ValueError:
                print("Invalid format. Use J1-J16.")
                
        # Select Panel Size Preset
        print("\nSelect Panel Size Preset:")
        for idx, key in enumerate(presets_keys, 1):
            print(f"  {idx}) {key} - {PANEL_PRESETS[key]['desc']}")
        print(f"  0) Custom Configuration")
        
        while True:
            preset_choice = input("Choice [1]: ").strip()
            if not preset_choice:
                preset_choice = "1"
            try:
                p_idx = int(preset_choice)
                if 0 <= p_idx <= len(presets_keys):
                    break
                print("Invalid choice.")
            except ValueError:
                print("Enter a number.")
                
        if p_idx > 0:
            layout[i] = {
                "phys_port": phys_port,
                "size": presets_keys[p_idx - 1]
            }
        else:
            # Custom settings
            print("\n--- Enter Custom Parameters ---")
            p_type = int(input("Panel Type ID (0=64x64, 1=stacked, 2=standard 1/16): ").strip())
            max_y = int(input("Max Scan Row Steps (e.g., 32, 16): ").strip())
            start_x = int(input("Col Shift Start Offset (e.g., 64, 0, 96): ").strip())
            layout[i] = {
                "phys_port": phys_port,
                "type": p_type,
                "max_y": max_y,
                "start_x": start_x,
                "size": "custom"
            }
            
    packet = build_config_packet(layout)
    
    # Save config to file
    config_data = {"layout": layout, "ip": ip}
    try:
        with open("layout_config.json", 'w') as f:
            json.dump(config_data, f, indent=2)
        print("\nConfiguration saved to layout_config.json")
    except Exception as e:
        print(f"Warning: could not save config file: {e}")
        
    # Send UDP Packet
    print(f"Sending configuration to {ip}:{DEFAULT_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (ip, DEFAULT_PORT))
        print("\nSUCCESS: Configuration packet sent successfully!")
        print("Active Mappings:")
        for idx, entry in enumerate(layout):
            if entry:
                size_str = entry.get("size", "custom")
                print(f"  Logical Driver {idx} -> Physical Port J{entry['phys_port']+1} ({size_str})")
    except Exception as e:
        print(f"\nERROR: Failed to send UDP packet: {e}")
    finally:
        sock.close()

def main():
    parser = argparse.ArgumentParser(description="Configure Colorlight Art-Net HUB75 Screen Layout")
    parser.add_argument("--ip", default=DEFAULT_IP, help=f"Destination IP address (default: {DEFAULT_IP})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Destination UDP Port (default: {DEFAULT_PORT})")
    parser.add_argument("--config", help="Path to JSON configuration file")
    parser.add_argument("--ports", nargs="+", help="Space-separated list of mappings, e.g. 0:J1:64x64 1:J8:stacked_32x64")
    parser.add_argument("-i", "--interactive", action="store_true", help="Start interactive configuration terminal")
    
    args = parser.parse_args()
    
    # If interactive is requested, or if no arguments are provided and stdin is a TTY
    if args.interactive or (not args.config and not args.ports and sys.stdin.isatty()):
        run_interactive()
        return
        
    layout = []
    
    if args.config:
        try:
            with open(args.config, 'r') as f:
                data = json.load(f)
                layout = data.get("layout", [])
        except Exception as e:
            print(f"Error reading config file: {e}")
            sys.exit(1)
            
    elif args.ports:
        for p in args.ports:
            try:
                parts = p.split(":")
                logical_id = int(parts[0])
                phys_j_str = parts[1].upper()
                size_preset = parts[2]
                
                if phys_j_str.startswith("J"):
                    phys_port = int(phys_j_str[1:]) - 1
                else:
                    phys_port = int(phys_j_str)
                    
                while len(layout) <= logical_id:
                    layout.append({})
                    
                layout[logical_id] = {
                    "phys_port": phys_port,
                    "size": size_preset
                }
            except Exception as e:
                print(f"Error parsing port mapping '{p}': {e}")
                sys.exit(1)
                
    packet = build_config_packet(layout)
    
    print(f"Sending configuration to {args.ip}:{args.port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (args.ip, args.port))
        print("Configuration packet sent successfully!")
        print("Active Port Mappings:")
        for idx, entry in enumerate(layout):
            if entry:
                print(f"  Logical Driver {idx} -> Physical Port J{entry['phys_port']+1} ({entry['size']})")
    except Exception as e:
        print(f"Failed to send UDP packet: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
