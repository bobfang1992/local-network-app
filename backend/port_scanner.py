import socket
import logging
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Common port to service mapping
COMMON_PORTS = {
    20: "FTP Data Transfer",
    21: "FTP Control",
    22: "SSH (Secure Shell)",
    23: "Telnet",
    25: "SMTP (Email)",
    53: "DNS",
    67: "DHCP Server",
    68: "DHCP Client",
    80: "HTTP (Web)",
    110: "POP3 (Email)",
    123: "NTP (Time)",
    143: "IMAP (Email)",
    161: "SNMP",
    443: "HTTPS (Secure Web)",
    445: "SMB/CIFS (File Sharing)",
    465: "SMTPS (Secure Email)",
    514: "Syslog",
    587: "SMTP (Email Submission)",
    631: "IPP (Printing)",
    993: "IMAPS (Secure Email)",
    995: "POP3S (Secure Email)",
    1433: "MS SQL Server",
    1521: "Oracle Database",
    3306: "MySQL Database",
    3389: "RDP (Remote Desktop)",
    5000: "UPnP",
    5432: "PostgreSQL Database",
    5900: "VNC (Remote Desktop)",
    6379: "Redis Database",
    8080: "HTTP Proxy/Alt",
    8443: "HTTPS Alt",
    8888: "HTTP Alt",
    9000: "Various Services",
    27017: "MongoDB Database",
}

# Default ports to scan (most common)
DEFAULT_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 465, 587, 631,
    993, 995, 3306, 3389, 5432, 5900, 8080, 8443
]


def scan_port(ip: str, port: int, timeout: float = 2.0, retries: int = 1) -> Dict:
    """
    Scan a single port on the given IP address.

    Args:
        ip: IP address to scan
        port: Port number to scan
        timeout: Socket timeout in seconds
        retries: Number of retries for failed connections

    Returns:
        Dict with port, status, and service information
    """
    for attempt in range(retries + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            result = sock.connect_ex((ip, port))
            sock.close()

            if result == 0:
                status = "open"
                break
            else:
                status = "closed"
                break
        except socket.timeout:
            sock.close()
            if attempt < retries:
                continue  # Retry
            status = "filtered"
        except socket.error as e:
            sock.close()
            logger.debug(f"Error scanning {ip}:{port} - {e}")
            if attempt < retries:
                continue  # Retry
            status = "error"

    service = COMMON_PORTS.get(port, "Unknown Service")

    return {
        "port": port,
        "status": status,
        "service": service
    }


def scan_ports(ip: str, ports: List[int] = None, timeout: float = 2.0, max_workers: int = 20) -> List[Dict]:
    """
    Scan multiple ports on a given IP address concurrently.

    Args:
        ip: IP address to scan
        ports: List of ports to scan (defaults to common ports)
        timeout: Socket timeout in seconds (default 2.0 for reliability)
        max_workers: Maximum number of concurrent threads (default 20 to avoid overwhelming network)

    Returns:
        List of dicts with port scan results (only open ports)
    """
    if ports is None:
        ports = DEFAULT_PORTS

    logger.info(f"Starting port scan on {ip} for {len(ports)} ports (timeout={timeout}s, workers={max_workers})")

    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all port scans with retry enabled
        future_to_port = {
            executor.submit(scan_port, ip, port, timeout, retries=1): port
            for port in ports
        }

        # Collect results as they complete
        for future in as_completed(future_to_port):
            try:
                result = future.result()
                # Only include open ports in results
                if result['status'] == 'open':
                    results.append(result)
                    logger.info(f"Found open port: {ip}:{result['port']} - {result['service']}")
            except Exception as e:
                port = future_to_port[future]
                logger.error(f"Error scanning port {port}: {e}")

    # Sort by port number
    results.sort(key=lambda x: x['port'])

    logger.info(f"Port scan complete on {ip}: {len(results)} open ports found")

    return results


def scan_all_ports(ip: str, timeout: float = 0.3, max_workers: int = 100) -> List[Dict]:
    """
    Scan all ports 1-65535 (use with caution - takes time!)

    Args:
        ip: IP address to scan
        timeout: Socket timeout in seconds (lower for faster scan)
        max_workers: Maximum number of concurrent threads

    Returns:
        List of dicts with port scan results (only open ports)
    """
    all_ports = list(range(1, 65536))
    return scan_ports(ip, all_ports, timeout, max_workers)
