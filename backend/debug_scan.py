#!/usr/bin/env python3
"""
Debug script to test network scanning capabilities
"""
import subprocess
import platform
import sys

print("=" * 60)
print("Network Scanning Debug Tool")
print("=" * 60)
print()

# Test 1: Check local IP
print("[1] Local IP Detection")
print("-" * 60)
from network_scanner import get_local_ip, get_network_prefix
local_ip = get_local_ip()
network = get_network_prefix(local_ip)
print(f"Local IP: {local_ip}")
print(f"Network:  {network}")
print()

# Test 2: Check system ARP cache
print("[2] System ARP Cache")
print("-" * 60)
try:
    if platform.system() == "Darwin":  # macOS
        result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=10)
        print(result.stdout)
        print(f"Total lines: {len(result.stdout.split(chr(10)))}")
    elif platform.system() == "Linux":
        result = subprocess.run(['arp', '-n'], capture_output=True, text=True, timeout=10)
        print(result.stdout)
    elif platform.system() == "Windows":
        result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=10)
        print(result.stdout)
except Exception as e:
    print(f"Error reading ARP cache: {e}")
print()

# Test 3: Try ARP scanning method
print("[3] ARP Cache Parsing Method")
print("-" * 60)
from network_scanner import scan_with_arp
devices = scan_with_arp()
print(f"Found {len(devices)} devices:")
for device in devices:
    print(f"  - {device['ip']:15s} {device['mac']:17s} {device['hostname']}")
print()

# Test 4: Check Scapy availability
print("[4] Scapy Availability")
print("-" * 60)
try:
    from scapy.all import ARP, Ether, srp
    print("✓ Scapy is installed and importable")

    # Test if we can create packets
    try:
        arp = ARP(pdst=network)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        packet = ether/arp
        print("✓ Can create ARP packets")
    except Exception as e:
        print(f"✗ Cannot create packets: {e}")

except ImportError as e:
    print(f"✗ Scapy not available: {e}")
print()

# Test 5: Try Scapy scanning (might need sudo)
print("[5] Scapy Active Scanning")
print("-" * 60)
try:
    from scapy.all import ARP, Ether, srp

    print(f"Scanning network: {network}")
    print("This may take a few seconds...")

    arp = ARP(pdst=network)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether/arp

    result = srp(packet, timeout=3, verbose=0)[0]

    print(f"Found {len(result)} devices via Scapy:")
    for sent, received in result:
        print(f"  - {received.psrc:15s} {received.hwsrc:17s}")

    if len(result) == 0:
        print("\n⚠ No devices found via Scapy!")
        print("This might be because:")
        print("  1. You need to run with sudo/elevated permissions")
        print("  2. Network configuration blocks ARP scanning")
        print("  3. No other devices are currently on the network")
        print("\nTry running: sudo python3 debug_scan.py")

except ImportError:
    print("✗ Scapy not installed")
except PermissionError as e:
    print(f"✗ Permission denied: {e}")
    print("\n⚠ Scapy needs elevated permissions!")
    print("Try running: sudo python3 debug_scan.py")
except Exception as e:
    print(f"✗ Error during Scapy scan: {e}")
    import traceback
    traceback.print_exc()
print()

# Test 6: Full scan_network function
print("[6] Full scan_network() Function")
print("-" * 60)
from network_scanner import scan_network
devices = scan_network()
print(f"Total devices found: {len(devices)}")
for device in devices:
    print(f"  - {device['ip']:15s} {device['mac']:17s} {device['hostname']}")
print()

print("=" * 60)
print("Debug Complete")
print("=" * 60)
print("\nRecommendations:")
print("1. If only 1 device found, try running: sudo python3 debug_scan.py")
print("2. Make sure other devices are active on your network")
print("3. Try pinging another device first: ping <device-ip>")
print("4. Check your router's connected devices list to verify")
