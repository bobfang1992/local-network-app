"""New-device alerts over ntfy.

## Why this keys on MAC, not IP

The rest of this app keys devices by IP (`devices.ip` is UNIQUE). That is fine
for tracking presence, but it is the wrong key for *alerting*: DHCP reassigns
addresses, so a phone that reconnects on a different IP looks brand new. Alerting
on that would push a notification every time a lease moved, and a notification
you learn to ignore is worse than none at all.

So alerts are deduplicated by MAC in their own table, independently of `devices`.

⚠️ Randomised MACs blunt this: a device that re-randomises looks new. In practice
Android/iOS derive a *persistent* MAC per network, so it is stable until the
network profile or a factory reset changes it — good enough to be useful, not
good enough to be an inventory.

## Two failure modes this deliberately guards

1. **First-run flood.** Every MAC already in the database would otherwise be
   "new" the first time this runs, producing one push per known device. The table
   is seeded from existing history instead, so only devices that appear *after*
   this feature went live can alert.

2. **Silent loss after a failed push.** The alerted-MAC row is written only after
   ntfy accepts the message. Flipping the flag on *detection* instead means a
   single failed delivery marks the device as alerted forever, and you never hear
   about it — the same trap `ea-health-watch` documents for its state machine.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

#: Where the topic comes from. The house convention is a 0600 file in $HOME;
#: the env var is for overriding it in a unit file or a test.
ENV_TOPIC = "LNA_NTFY_TOPIC"
TOPIC_FILE = Path.home() / ".ntfy-topic"

TIMEOUT_S = 10

#: Default ntfy server. Overridable per call via LNA_NTFY_BASE.
DEFAULT_NTFY_BASE = "https://ntfy.sh"


def _base() -> str:
    """⚠️ Read at call time, not import time.

    A module-level `NTFY_BASE = os.environ.get(...)` binds the value when the
    module is first imported, so anything that sets the variable afterwards —
    a test, a unit file loaded later — has no effect at all. The seam looks
    like it exists and silently does not. My own test caught this: it pointed
    the base at a dead port to prove a failed push is not recorded, and the
    push went to the real server instead and *was* recorded.
    """
    return os.environ.get("LNA_NTFY_BASE", "").strip() or DEFAULT_NTFY_BASE


def topic() -> str | None:
    """The ntfy topic, or None when alerting is not configured.

    Not configured is a normal state, not an error: the scanner is useful
    without alerts, so a missing topic logs once and is otherwise silent.
    """
    env = os.environ.get(ENV_TOPIC, "").strip()
    if env:
        return env
    try:
        value = TOPIC_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init(db_path: str, known_macs: Iterable[str] | None = None) -> int:
    """Create the dedup table and, on first creation, seed it.

    Returns how many MACs were seeded — 0 on every later call.

    ⚠️ The seeding only happens when the table is created. Re-seeding on every
       start would be harmless today but would silently swallow a genuinely new
       device if this ever ran before its first scan completed.
    """
    with _connect(db_path) as conn:
        existed = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alerted_macs'"
        ).fetchone()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerted_macs (
                mac TEXT PRIMARY KEY,
                first_alerted TEXT NOT NULL,
                ip TEXT,
                hostname TEXT,
                vendor TEXT,
                seeded INTEGER DEFAULT 0
            )
        """)
        if existed:
            return 0
        now = datetime.now().isoformat()
        macs = list(known_macs or [])
        if not macs:
            macs = [
                r["mac"] for r in conn.execute(
                    "SELECT DISTINCT mac FROM devices WHERE mac IS NOT NULL AND mac != ''"
                )
            ]
        rows = [(m, now, None, None, None, 1) for m in macs if m and m != "unknown"]
        conn.executemany(
            "INSERT OR IGNORE INTO alerted_macs (mac, first_alerted, ip, hostname, vendor, seeded)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        logger.info(
            "alerted_macs created and seeded with %d MAC(s) already in history — "
            "only devices appearing from now on will alert.",
            len(rows),
        )
        return len(rows)


def _already_alerted(conn: sqlite3.Connection, mac: str) -> bool:
    return conn.execute("SELECT 1 FROM alerted_macs WHERE mac = ?", (mac,)).fetchone() is not None


def _push(topic_name: str, title: str, body: str, tags: str = "warning") -> bool:
    """Send one ntfy message. Returns whether ntfy accepted it."""
    import requests

    url = f"{_base()}/{topic_name}"
    try:
        r = requests.post(
            url,
            data=body.encode("utf-8"),
            headers={"Title": title, "Tags": tags, "Priority": "default"},
            timeout=TIMEOUT_S,
        )
    except Exception as exc:
        # ⚠️ Never log the exception verbatim: requests puts the full URL in it,
        #    and the URL *is* the topic — which is kept in a 0600 file precisely
        #    because anyone who knows it can publish to the owner's phone.
        #    Logs are not 0600. Report the base and the error type only.
        logger.warning(
            "ntfy push failed (%s) to %s/<topic redacted>", type(exc).__name__, _base()
        )
        return False
    if not r.ok:
        logger.warning("ntfy refused the message: HTTP %s", r.status_code)
        return False
    return True


def alert_new_devices(db_path: str, devices: list[dict]) -> int:
    """Push one alert per MAC not seen before. Returns how many were pushed.

    ⚠️ The row is inserted only after a successful push — see the module docstring.
    """
    name = topic()
    if not name:
        return 0
    sent = 0
    with _connect(db_path) as conn:
        for d in devices:
            mac = (d.get("mac") or "").strip()
            if not mac or mac == "unknown":
                continue
            if _already_alerted(conn, mac):
                continue
            ip = d.get("ip") or "?"
            host = d.get("hostname") or "Unknown"
            vendor = d.get("vendor") or "unknown vendor"
            body = f"{ip}\n{host}\n{mac}\n{vendor}"
            if not _push(name, "New device on the network", body):
                # Deliberately not recorded: we want to try again next scan.
                continue
            conn.execute(
                "INSERT OR IGNORE INTO alerted_macs (mac, first_alerted, ip, hostname, vendor, seeded)"
                " VALUES (?, ?, ?, ?, ?, 0)",
                (mac, datetime.now().isoformat(), ip, host, vendor),
            )
            sent += 1
            logger.info("Alerted on new device %s (%s / %s)", mac, ip, host)
    return sent
