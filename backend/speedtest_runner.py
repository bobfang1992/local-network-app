"""Periodic internet speed test.

## Why this is not on the scan loop

The device scan runs every ~40s and costs almost nothing. A speed test
**saturates the household's uplink for the better part of a minute** — running it
on the same cadence would make the connection unusable and the numbers
meaningless. It gets its own slow timer, and defaults to every 6 hours.

## ⚠️ Pin the server, or the history is not comparable

speedtest-cli picks a server per run. Different servers are different distances
and different capacity, so an unpinned series mixes measurements that cannot be
compared — a drop in the chart would just as likely be a different endpoint as a
slower line. `LNA_SPEEDTEST_SERVER` pins it; the first successful run records
whichever server was chosen so the choice is at least visible.

## ⚠️ What these numbers are and are not

They are a *trend* signal for one host on wired ethernet. They are not the
line's rated capacity: the measured server here sits 273 km away, and
speedtest-cli's single-stream transfer under-reports on fast links. Treat a
change over time as meaningful; treat the absolute value as a floor.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

ENV_INTERVAL_H = "LNA_SPEEDTEST_INTERVAL_HOURS"
ENV_SERVER = "LNA_SPEEDTEST_SERVER"
DEFAULT_INTERVAL_H = 6
RUN_TIMEOUT_S = 180


def interval_hours() -> float:
    try:
        return max(0.25, float(os.environ.get(ENV_INTERVAL_H, DEFAULT_INTERVAL_H)))
    except ValueError:
        return DEFAULT_INTERVAL_H


def available() -> bool:
    return shutil.which("speedtest-cli") is not None


def init(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS speedtests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                download_mbps REAL,
                upload_mbps REAL,
                ping_ms REAL,
                server_id TEXT,
                server_name TEXT,
                server_sponsor TEXT,
                server_km REAL,
                isp TEXT,
                ok INTEGER NOT NULL DEFAULT 1,
                error TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_speedtests_run_at ON speedtests(run_at)")


def _record(db_path: str, row: dict) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO speedtests (run_at, download_mbps, upload_mbps, ping_ms,"
            " server_id, server_name, server_sponsor, server_km, isp, ok, error)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (row["run_at"], row.get("download_mbps"), row.get("upload_mbps"),
             row.get("ping_ms"), row.get("server_id"), row.get("server_name"),
             row.get("server_sponsor"), row.get("server_km"), row.get("isp"),
             1 if row.get("ok") else 0, row.get("error")),
        )


def run_once(db_path: str) -> dict:
    """Run one test and record it — failures included.

    ⚠️ A failed run is recorded too. If only successes were stored, an outage
       would look like a gap, and a gap looks exactly like "the monitor was off"
       — which this database already cannot distinguish for device history.
    """
    now = datetime.now().isoformat()
    if not available():
        row = {"run_at": now, "ok": False, "error": "speedtest-cli not installed"}
        _record(db_path, row)
        return row

    cmd = ["speedtest-cli", "--json"]
    server = os.environ.get(ENV_SERVER, "").strip()
    if server:
        cmd += ["--server", server]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=RUN_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        row = {"run_at": now, "ok": False, "error": f"timed out after {RUN_TIMEOUT_S}s"}
        _record(db_path, row)
        logger.warning("Speed test timed out")
        return row

    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()[-200:]
        row = {"run_at": now, "ok": False, "error": f"exit {p.returncode}: {err}"}
        _record(db_path, row)
        logger.warning("Speed test failed: %s", err or f"exit {p.returncode}")
        return row

    try:
        d = json.loads(p.stdout or b"{}")
        s = d.get("server") or {}
        row = {
            "run_at": now,
            "download_mbps": round(d["download"] / 1e6, 2),
            "upload_mbps": round(d["upload"] / 1e6, 2),
            "ping_ms": round(d["ping"], 1),
            "server_id": str(s.get("id") or ""),
            "server_name": s.get("name"),
            "server_sponsor": s.get("sponsor"),
            "server_km": float(s.get("d") or 0) or None,
            "isp": (d.get("client") or {}).get("isp"),
            "ok": True,
        }
    except Exception as exc:
        row = {"run_at": now, "ok": False, "error": f"unparsable output: {exc}"}
        _record(db_path, row)
        logger.warning("Speed test output could not be parsed: %s", exc)
        return row

    _record(db_path, row)
    logger.info(
        "Speed test: %.1f down / %.1f up Mbps, %.1f ms (%s)",
        row["download_mbps"], row["upload_mbps"], row["ping_ms"], row["server_sponsor"],
    )
    return row


def history(db_path: str, limit: int = 50) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM speedtests ORDER BY run_at DESC LIMIT ?", (limit,))]
