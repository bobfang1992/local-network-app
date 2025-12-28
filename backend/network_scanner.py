import platform
import socket
import os
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

def get_local_ip():
    """Get the local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"

def get_network_prefix(ip):
    """Get network prefix from IP (e.g., 192.168.1.0/24)"""
    parts = ip.split('.')
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

def resolve_hostname(ip: str, timeout: float = 0.5) -> str:
    """
    Resolve hostname from IP address using reverse DNS lookup.
    Returns 'Unknown' if hostname cannot be resolved.
    """
    try:
        # Set a timeout for the DNS lookup
        socket.setdefaulttimeout(timeout)
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname
    except (socket.herror, socket.gaierror, socket.timeout):
        return "Unknown"
    except Exception as e:
        logger.debug(f"Error resolving hostname for {ip}: {e}")
        return "Unknown"
    finally:
        socket.setdefaulttimeout(None)

def read_arp_cache_file() -> List[Dict]:
    """
    Read ARP cache directly from system files (no subprocess).
    Works on Linux by reading /proc/net/arp
    """
    devices = []

    try:
        if platform.system() == "Linux":
            # Read /proc/net/arp directly
            if os.path.exists('/proc/net/arp'):
                with open('/proc/net/arp', 'r') as f:
                    lines = f.readlines()[1:]  # Skip header
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 4:
                            ip = parts[0]
                            mac = parts[3]
                            if mac != "00:00:00:00:00:00" and not ip.startswith("169.254"):
                                hostname = resolve_hostname(ip)
                                devices.append({
                                    "ip": ip,
                                    "mac": mac,
                                    "hostname": hostname,
                                    "status": "online"
                                })
        else:
            logger.debug("ARP cache file reading not supported on this platform")

    except Exception as e:
        logger.error(f"Error reading ARP cache file: {e}")

    return devices

def scan_with_scapy(timeout: int = 5, retry: int = 3) -> List[Dict]:
    """
    Active ARP scanning using Scapy (pure Python, no subprocess).

    This is the preferred method as it:
    - Actively scans the network
    - Finds all devices, even those not in ARP cache
    - Uses pure Python (no subprocess)

    Note: Requires elevated permissions (sudo) on most systems to access raw sockets.

    Args:
        timeout: Seconds to wait for responses (increased from 3 to 5 for sleeping devices)
        retry: Number of times to retry unanswered requests (increased from 2 to 3)
    """
    devices = []

    try:
        from scapy.all import ARP, Ether, srp, conf

        # Suppress Scapy warnings
        conf.verb = 0

        local_ip = get_local_ip()
        network = get_network_prefix(local_ip)

        logger.info(f"Starting Scapy ARP scan on {network} (timeout={timeout}s, retry={retry})")

        # Create ARP request packet
        arp = ARP(pdst=network)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        packet = ether / arp

        # Send packet and receive responses
        # Increased timeout and retries to catch devices in power-saving mode
        answered, unanswered = srp(packet, timeout=timeout, verbose=0, retry=retry)

        logger.info(f"Scapy scan complete: {len(answered)} devices responded")

        for sent, received in answered:
            ip = received.psrc
            mac = received.hwsrc

            # Filter out unwanted addresses
            if (not ip.startswith("169.254") and      # Skip link-local
                not ip.startswith("224.") and          # Skip multicast
                mac != "ff:ff:ff:ff:ff:ff" and        # Skip broadcast
                not mac.startswith("01:00:5e")):      # Skip multicast MAC

                # Resolve hostname via reverse DNS
                hostname = resolve_hostname(ip)

                devices.append({
                    "ip": ip,
                    "mac": mac,
                    "hostname": hostname,
                    "status": "online"
                })

    except ImportError:
        logger.error("Scapy is not installed")
        raise ImportError("Scapy library is required for network scanning")

    except PermissionError as e:
        logger.warning(f"Permission denied for Scapy scan: {e}")
        raise PermissionError(
            "Network scanning requires elevated permissions. "
            "Please run the backend with sudo: sudo python main.py"
        )

    except Exception as e:
        logger.error(f"Error during Scapy scan: {e}")
        raise

    return devices

def scan_network() -> List[Dict]:
    """
    Scan the local network and return list of devices.

    Strategy:
    1. Try Scapy active scanning (best, but needs sudo)
    2. Fallback to reading ARP cache file on Linux
    3. Return at least the local machine
    """
    devices = []
    scan_method = "none"

    # Try Scapy first (most comprehensive)
    try:
        devices = scan_with_scapy(timeout=3)
        scan_method = "scapy"
        logger.info(f"Scapy scan successful: found {len(devices)} devices")

    except PermissionError as e:
        logger.warning(f"Scapy requires sudo: {e}")
        # Try reading ARP cache file (Linux only, no sudo needed)
        devices = read_arp_cache_file()
        if devices:
            scan_method = "arp_cache_file"
            logger.info(f"ARP cache file read successful: found {len(devices)} devices")
        else:
            logger.warning("No fallback method available. Run with sudo for full scanning.")

    except ImportError as e:
        logger.error(f"Scapy not available: {e}")
        devices = read_arp_cache_file()
        scan_method = "arp_cache_file" if devices else "none"

    except Exception as e:
        logger.error(f"Unexpected error during scan: {e}")
        # Try fallback
        devices = read_arp_cache_file()
        scan_method = "arp_cache_file" if devices else "none"

    # Always add local machine info
    local_ip = get_local_ip()
    local_hostname = socket.gethostname()

    # Check if local machine is already in the list
    local_exists = any(d['ip'] == local_ip for d in devices)

    if not local_exists:
        devices.insert(0, {
            "ip": local_ip,
            "mac": "local",
            "hostname": f"{local_hostname} (This Device)",
            "status": "online"
        })

    logger.info(f"Total devices found: {len(devices)} (method: {scan_method})")

    return devices
