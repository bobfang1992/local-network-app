import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Store database in user's home directory, separate from code
DB_DIR = Path.home() / ".local-network" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DB_DIR / "devices.db")

logger.info(f"Database location: {DB_PATH}")


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_database():
    """Initialize the database schema"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Create devices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT UNIQUE NOT NULL,
                mac TEXT NOT NULL,
                hostname TEXT,
                notes TEXT DEFAULT '',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_seen_online TEXT,
                total_scans INTEGER DEFAULT 0,
                scans_seen_online INTEGER DEFAULT 0,
                scans_seen_offline INTEGER DEFAULT 0,
                consecutive_offline INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Add notes column to existing databases (migration)
        try:
            cursor.execute("ALTER TABLE devices ADD COLUMN notes TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # Add consecutive_online column for streak tracking (migration)
        try:
            cursor.execute("ALTER TABLE devices ADD COLUMN consecutive_online INTEGER DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # Create index on IP for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip)
        """)

        # Create scans table to track scan history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_time TEXT NOT NULL,
                devices_found INTEGER DEFAULT 0,
                scan_method TEXT
            )
        """)

        # Create categorization log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categorization_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER,
                ip TEXT NOT NULL,
                hostname TEXT,
                total_scans INTEGER,
                scans_seen_online INTEGER,
                appearance_rate REAL,
                category TEXT,
                device_status TEXT,
                reason TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scans(id)
            )
        """)

        # Create index on categorization log
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cat_log_ip ON categorization_log(ip)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cat_log_scan ON categorization_log(scan_id)
        """)

        # Create port scans table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS port_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                status TEXT NOT NULL,
                service TEXT,
                scan_time TEXT NOT NULL,
                UNIQUE(ip, port, scan_time)
            )
        """)

        # Create index on port scans
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_port_scans_ip ON port_scans(ip)
        """)

        conn.commit()
        logger.info(f"Database initialized at {DB_PATH}")


def record_scan(devices_found: int, scan_method: str = "scapy") -> int:
    """Record a scan event and return scan_id"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scans (scan_time, devices_found, scan_method)
            VALUES (?, ?, ?)
        """, (datetime.now().isoformat(), devices_found, scan_method))
        return cursor.lastrowid


def get_total_scans() -> int:
    """Get total number of scans performed"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM scans")
        result = cursor.fetchone()
        return result['count'] if result else 0


def update_device(ip: str, mac: str, hostname: str, is_online: bool = True):
    """
    Update or insert device record.

    Args:
        ip: Device IP address
        mac: Device MAC address
        hostname: Device hostname
        is_online: Whether device is currently online
    """
    now = datetime.now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if device exists
        cursor.execute("SELECT * FROM devices WHERE ip = ?", (ip,))
        existing = cursor.fetchone()

        if existing:
            # Update existing device
            if is_online:
                cursor.execute("""
                    UPDATE devices SET
                        mac = ?,
                        hostname = ?,
                        last_seen = ?,
                        last_seen_online = ?,
                        scans_seen_online = scans_seen_online + 1,
                        consecutive_offline = 0,
                        consecutive_online = consecutive_online + 1,
                        updated_at = ?
                    WHERE ip = ?
                """, (mac, hostname, now, now, now, ip))
            else:
                cursor.execute("""
                    UPDATE devices SET
                        last_seen = ?,
                        scans_seen_offline = scans_seen_offline + 1,
                        consecutive_offline = consecutive_offline + 1,
                        consecutive_online = 0,
                        updated_at = ?
                    WHERE ip = ?
                """, (now, now, ip))
        else:
            # Insert new device
            cursor.execute("""
                INSERT INTO devices (
                    ip, mac, hostname, first_seen, last_seen, last_seen_online,
                    total_scans, scans_seen_online, scans_seen_offline,
                    consecutive_offline, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 0, ?, ?)
            """, (
                ip, mac, hostname, now, now, now if is_online else None,
                1 if is_online else 0,
                1 if is_online else 0,
                now, now
            ))


def increment_total_scans():
    """Increment total_scans counter for all devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE devices SET total_scans = total_scans + 1")


def get_device_history(ip: str) -> Optional[Dict]:
    """Get device history from database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE ip = ?", (ip,))
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None


def get_all_known_devices() -> List[Dict]:
    """Get all devices from database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY last_seen DESC")
        return [dict(row) for row in cursor.fetchall()]


def calculate_device_category(device_data: Dict, is_online: bool = True, recent_streak: int = 0) -> tuple[str, str]:
    """
    Calculate device category based on historical data with recent trend weighting.
    Returns (category, reason) for debugging.

    Simplified Categories:
    - new: First 3 scans (truly new device)
    - regular: Seen in >70% of scans OR on a strong recent streak
    - occasional: Seen in 30-70% of scans
    - rare: Seen in <30% of scans
    - offline: Currently not responding

    Recent Streak Bonus: If a device is online and has been consistently online
    for the last N scans, it gets upgraded to "regular" even if historical rate is lower.
    """
    total_scans = device_data.get('total_scans', 0)
    scans_seen_online = device_data.get('scans_seen_online', 0)
    consecutive_offline = device_data.get('consecutive_offline', 0)

    # If offline, return offline category
    if not is_online:
        if total_scans == 0:
            return 'offline', 'offline with no history'
        appearance_rate = scans_seen_online / total_scans if total_scans > 0 else 0
        return 'offline', f'offline (historically {appearance_rate:.0%} appearance)'

    # Truly new devices (≤3 scans)
    if total_scans <= 3:
        return 'new', f'new device (seen {total_scans} times)'

    # Calculate appearance rate for established devices
    appearance_rate = scans_seen_online / total_scans if total_scans > 0 else 0

    # Recent streak bonus: If device has been consistently online recently
    # and has enough history, upgrade to regular
    # Threshold: 15+ consecutive scans online AND total_scans >= 20
    if recent_streak >= 15 and total_scans >= 20 and appearance_rate >= 0.4:
        return 'regular', f'regular device (recent streak: {recent_streak} scans, {appearance_rate:.0%} historical)'

    # Standard classification with slightly relaxed thresholds
    if appearance_rate >= 0.65:  # Lowered from 0.7 to 0.65
        return 'regular', f'regular device ({appearance_rate:.0%} appearance)'
    elif appearance_rate >= 0.3:
        return 'occasional', f'occasional device ({appearance_rate:.0%} appearance)'
    else:
        return 'rare', f'rare device ({appearance_rate:.0%} appearance)'


def log_categorization(scan_id: int, ip: str, hostname: str, total_scans: int,
                       scans_seen_online: int, appearance_rate: float,
                       category: str, device_status: str, reason: str):
    """Log device categorization decision"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO categorization_log (
                scan_id, ip, hostname, total_scans, scans_seen_online,
                appearance_rate, category, device_status, reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scan_id, ip, hostname, total_scans, scans_seen_online,
            appearance_rate, category, device_status, reason,
            datetime.now().isoformat()
        ))


def get_categorization_log(limit: int = 100) -> List[Dict]:
    """Get recent categorization log entries"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM categorization_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def update_device_notes(ip: str, notes: str):
    """Update notes for a device"""
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE devices SET notes = ?, updated_at = ?
            WHERE ip = ?
        """, (notes, now, ip))


def get_database_stats() -> Dict:
    """Get database statistics"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM devices")
        total_devices = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM scans")
        total_scans = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count FROM devices
            WHERE datetime(last_seen_online) > datetime('now', '-1 day')
        """)
        active_24h = cursor.fetchone()['count']

        return {
            'total_devices': total_devices,
            'total_scans': total_scans,
            'active_24h': active_24h
        }


def save_port_scan_results(ip: str, results: List[Dict], pihole_info: Dict = None):
    """Save port scan results to database"""
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        for result in results:
            cursor.execute("""
                INSERT OR REPLACE INTO port_scans (ip, port, status, service, scan_time)
                VALUES (?, ?, ?, ?, ?)
            """, (ip, result['port'], result['status'], result.get('service', ''), now))

        # Save Pi-hole info if detected
        if pihole_info:
            # Add pihole_detected column to devices table if it doesn't exist
            try:
                cursor.execute("ALTER TABLE devices ADD COLUMN pihole_detected INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE devices ADD COLUMN pihole_admin_url TEXT")
            except:
                pass  # Column already exists

            cursor.execute("""
                UPDATE devices
                SET pihole_detected = 1,
                    pihole_admin_url = ?,
                    updated_at = ?
                WHERE ip = ?
            """, (pihole_info.get('admin_url'), now, ip))


def get_latest_port_scan(ip: str) -> Optional[Dict]:
    """Get the most recent port scan results for an IP"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Get the latest scan time
        cursor.execute("""
            SELECT MAX(scan_time) as latest_scan
            FROM port_scans
            WHERE ip = ?
        """, (ip,))
        row = cursor.fetchone()

        if not row or not row['latest_scan']:
            return None

        latest_scan = row['latest_scan']

        # Get all ports from that scan
        cursor.execute("""
            SELECT port, status, service
            FROM port_scans
            WHERE ip = ? AND scan_time = ?
            ORDER BY port
        """, (ip, latest_scan))

        ports = [dict(row) for row in cursor.fetchall()]

        return {
            'ip': ip,
            'scan_time': latest_scan,
            'ports': ports
        }
