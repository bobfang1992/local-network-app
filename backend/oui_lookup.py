import csv
import logging
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

OUI_CSV_PATHS = [
    Path(__file__).with_name("oui.csv"),
    Path.home() / ".local-network" / "oui.csv",
]

OUI_TXT_PATHS = [
    Path.home() / ".local-network" / "oui.txt",
]

_OUI_CACHE: Optional[Dict[str, str]] = None
_LOGGED_MISSING = False


def _normalize_prefix(raw: str) -> Optional[str]:
    if not raw:
        return None
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", raw).upper()
    if len(cleaned) < 6:
        return None
    return cleaned[:6]


def _load_from_csv(path: Path) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        first_row = next(reader, None)
        if not first_row:
            return entries

        # IEEE format: Registry,Assignment,Organization Name,Organization Address
        if "Assignment" in first_row and "Organization Name" in first_row:
            dict_reader = csv.DictReader(handle, fieldnames=first_row)
            for row in dict_reader:
                prefix = _normalize_prefix(row.get("Assignment", ""))
                if not prefix:
                    continue
                vendor = (row.get("Organization Name") or "").strip()
                if vendor:
                    entries[prefix] = vendor
            return entries

        # Fallback: assume two-column CSV (prefix, vendor)
        prefix = _normalize_prefix(first_row[0]) if first_row else None
        vendor = first_row[1].strip() if first_row and len(first_row) > 1 else ""
        if prefix and vendor:
            entries[prefix] = vendor
        for row in reader:
            if not row:
                continue
            prefix = _normalize_prefix(row[0])
            if not prefix:
                continue
            vendor = row[1].strip() if len(row) > 1 else ""
            if vendor:
                entries[prefix] = vendor
    return entries


def _load_from_txt(path: Path) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    with path.open() as handle:
        for line in handle:
            if "(hex)" not in line and "(base 16)" not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            prefix = _normalize_prefix(parts[0])
            if not prefix:
                continue
            vendor = line.split(")", 1)[-1].strip()
            if vendor:
                entries[prefix] = vendor
    return entries


def _load_oui_db() -> Dict[str, str]:
    entries: Dict[str, str] = {}
    for path in OUI_CSV_PATHS:
        if path.exists():
            entries.update(_load_from_csv(path))
    for path in OUI_TXT_PATHS:
        if path.exists():
            entries.update(_load_from_txt(path))
    if entries:
        logger.info(f"Loaded {len(entries)} OUI entries for vendor lookups.")
    return entries


def get_vendor_for_mac(mac: str) -> Optional[str]:
    global _OUI_CACHE, _LOGGED_MISSING
    if _OUI_CACHE is None:
        _OUI_CACHE = _load_oui_db()
        if not _OUI_CACHE and not _LOGGED_MISSING:
            logger.info("No OUI database found. Add oui.csv to backend/ or ~/.local-network/oui.csv for vendor lookups.")
            _LOGGED_MISSING = True
    if not mac:
        return None
    prefix = _normalize_prefix(mac)
    if not prefix:
        return None
    return _OUI_CACHE.get(prefix) if _OUI_CACHE else None
