#!/usr/bin/env python3
import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Recalculate device stats from categorization_log.")
    parser.add_argument("--db", default=str(Path.home() / ".local-network" / "db" / "devices.db"))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    counts_online = defaultdict(int)
    counts_offline = defaultdict(int)
    consecutive_status = {}
    consecutive_count = defaultdict(int)
    consecutive_done = set()

    cursor.execute("""
        SELECT ip, device_status
        FROM categorization_log
        WHERE device_status IN ('online', 'offline')
        ORDER BY timestamp DESC
    """)

    for row in cursor:
        ip = row["ip"]
        status = row["device_status"]

        if status == "online":
            counts_online[ip] += 1
        elif status == "offline":
            counts_offline[ip] += 1

        if ip not in consecutive_status:
            consecutive_status[ip] = status
            consecutive_count[ip] = 1
        elif ip not in consecutive_done:
            if status == consecutive_status[ip]:
                consecutive_count[ip] += 1
            else:
                consecutive_done.add(ip)

    cursor.execute("SELECT ip FROM devices")
    device_ips = [row["ip"] for row in cursor.fetchall()]
    now = datetime.now().isoformat()

    for ip in device_ips:
        online = counts_online.get(ip, 0)
        offline = counts_offline.get(ip, 0)
        total = online + offline

        status = consecutive_status.get(ip)
        consecutive_online = consecutive_count[ip] if status == "online" else 0
        consecutive_offline = consecutive_count[ip] if status == "offline" else 0

        cursor.execute("""
            UPDATE devices
            SET scans_seen_online = ?,
                scans_seen_offline = ?,
                total_scans = ?,
                consecutive_online = ?,
                consecutive_offline = ?,
                updated_at = ?
            WHERE ip = ?
        """, (online, offline, total, consecutive_online, consecutive_offline, now, ip))

    conn.commit()
    conn.close()
    print(f"Recalculated stats for {len(device_ips)} devices in {db_path}")


if __name__ == "__main__":
    main()
