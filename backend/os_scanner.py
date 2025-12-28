import logging
import re
import shutil
import subprocess
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def _parse_os_output(output: str) -> Optional[Dict]:
    if not output:
        return None

    if "OS detection requires root privileges" in output:
        return {"error": "OS detection requires sudo/root privileges."}

    aggressive_match = re.search(r"Aggressive OS guesses:\s*(.+)", output)
    if aggressive_match:
        guess_block = aggressive_match.group(1)
        guess_match = re.search(r"(.+?)\s+\((\d+)%\)", guess_block)
        if guess_match:
            return {"os_guess": guess_match.group(1).strip(), "os_accuracy": int(guess_match.group(2))}
        return {"os_guess": guess_block.strip(), "os_accuracy": None}

    details_match = re.search(r"OS details:\s*(.+)", output)
    if details_match:
        return {"os_guess": details_match.group(1).strip(), "os_accuracy": None}

    running_match = re.search(r"Running:\s*(.+)", output)
    if running_match:
        return {"os_guess": running_match.group(1).strip(), "os_accuracy": None}

    if "No OS matches for host" in output:
        return {"error": "No OS match found."}

    return None


def scan_os(ip: str, timeout_seconds: int = 30) -> Dict:
    if not shutil.which("nmap"):
        return {"error": "nmap is not installed. Install it to enable OS detection."}

    timeout_arg = f"{timeout_seconds}s"
    cmd = [
        "nmap",
        "-O",
        "--osscan-guess",
        "--max-os-tries",
        "1",
        "-n",
        "-Pn",
        "--host-timeout",
        timeout_arg,
        ip,
    ]

    logger.info(f"Running OS scan: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds + 5
        )
    except subprocess.TimeoutExpired:
        return {"error": "OS scan timed out."}

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    parsed = _parse_os_output(output)
    if not parsed:
        return {"error": "OS scan did not return a recognizable fingerprint."}

    if "error" in parsed:
        return parsed

    return {
        "os_guess": parsed.get("os_guess"),
        "os_accuracy": parsed.get("os_accuracy"),
    }
