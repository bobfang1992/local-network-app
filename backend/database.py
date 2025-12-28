import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "devices.db")


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

        conn.commit()
        logger.info(f"Database initialized at {DB_PATH}")


def record_scan(devices_found: int, scan_method: str = "scapy"):
    """Record a scan event"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scans (scan_time, devices_found, scan_method)
            VALUES (?, ?, ?)
        """, (datetime.now().isoformat(), devices_found, scan_method))


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
                        updated_at = ?
                    WHERE ip = ?
                """, (mac, hostname, now, now, now, ip))
            else:
                cursor.execute("""
                    UPDATE devices SET
                        last_seen = ?,
                        scans_seen_offline = scans_seen_offline + 1,
                        consecutive_offline = consecutive_offline + 1,
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


def calculate_device_category(device_data: Dict) -> str:
    """
    Calculate device category based on historical data.

    Categories:
    - regular: Seen in >70% of scans (frequent device)
    - occasional: Seen in 30-70% of scans
    - rare: Seen in <30% of scans
    - new: First time seeing this device
    """
    total_scans = device_data.get('total_scans', 0)
    scans_seen_online = device_data.get('scans_seen_online', 0)

    if total_scans == 0:
        return 'new'

    # Calculate appearance rate
    appearance_rate = scans_seen_online / total_scans if total_scans > 0 else 0

    # Need at least 5 scans to classify as regular/occasional
    if total_scans < 5:
        return 'new'

    if appearance_rate >= 0.7:
        return 'regular'
    elif appearance_rate >= 0.3:
        return 'occasional'
    else:
        return 'rare'


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
