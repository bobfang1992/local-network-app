import logging
import socket
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def discover_ssdp(target_ip: Optional[str] = None, timeout_seconds: float = 2.0) -> Dict[str, Dict]:
    message = "\r\n".join([
        "M-SEARCH * HTTP/1.1",
        "HOST: 239.255.255.250:1900",
        "MAN: \"ssdp:discover\"",
        "MX: 1",
        "ST: ssdp:all",
        "",
        ""
    ]).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout_seconds)

    try:
        sock.sendto(message, ("239.255.255.250", 1900))
    except Exception as exc:
        logger.error(f"Failed to send SSDP discovery: {exc}")
        sock.close()
        return {}

    responses: Dict[str, Dict] = {}
    start = time.time()

    while time.time() - start < timeout_seconds:
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            break
        except Exception as exc:
            logger.debug(f"SSDP receive error: {exc}")
            break

        ip = addr[0]
        if target_ip and ip != target_ip:
            continue

        text = data.decode("utf-8", errors="ignore")
        headers = {}
        for line in text.split("\r\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        responses[ip] = {
            "server": headers.get("server", ""),
            "location": headers.get("location", ""),
            "st": headers.get("st", ""),
            "usn": headers.get("usn", "")
        }

    sock.close()
    return responses
