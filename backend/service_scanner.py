import logging
import re
import shutil
import subprocess
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _parse_service_output(output: str) -> Dict[int, Dict[str, Optional[str]]]:
    results: Dict[int, Dict[str, Optional[str]]] = {}
    for line in output.splitlines():
        line = line.strip()
        match = re.match(r"^(\d+)/tcp\s+open\s+(\S+)\s*(.*)$", line)
        if match:
            port = int(match.group(1))
            service = match.group(2).strip()
            details = match.group(3).strip()
            results[port] = {
                "service": service,
                "details": details or None
            }
    return results


def scan_services(ip: str, ports: List[int], timeout_seconds: int = 20) -> Dict:
    if not ports:
        return {"services": {}}

    if not shutil.which("nmap"):
        return {"error": "nmap is not installed. Install it to enable service detection."}

    port_list = ",".join(str(p) for p in ports)
    timeout_arg = f"{timeout_seconds}s"
    cmd = [
        "nmap",
        "-sV",
        "--version-intensity",
        "2",
        "-Pn",
        "-n",
        "--host-timeout",
        timeout_arg,
        "-p",
        port_list,
        ip,
    ]

    logger.info(f"Running service scan: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds + 5
        )
    except subprocess.TimeoutExpired:
        return {"error": "Service scan timed out."}

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    services = _parse_service_output(output)
    return {"services": services}
