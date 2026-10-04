from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from network_scanner import scan_network
from port_scanner import scan_ports
from pi_hole_detector import check_if_pihole
import notifier
import speedtest_runner
import presence
import sqlite3
from database import (
    DB_PATH, init_database, update_device,
    get_device_history, get_all_known_devices, calculate_device_category,
    record_scan, get_database_stats, get_total_scans, update_device_notes,
    log_categorization, get_categorization_log, save_port_scan_results,
    get_latest_port_scan, update_device_os, update_device_os_error,
    update_device_ssdp, log_scan_event
)
from oui_lookup import get_vendor_for_mac
from os_scanner import scan_os
from service_scanner import scan_services
from ssdp_scanner import discover_ssdp
import uvicorn
import logging
import sys
import os
import asyncio
import json
from typing import List, Set
from datetime import datetime, timedelta
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Initialize database
init_database()
try:
    speedtest_runner.init(DB_PATH)
    logger.info(
        "Speed test: %s, every %.1fh",
        "enabled" if speedtest_runner.available() else "speedtest-cli not installed",
        speedtest_runner.interval_hours(),
    )
except Exception as _exc:
    logger.warning(f"Could not initialise speed tests: {_exc}")
# 建新设备告警的去重表。
# ⚠️ 首次创建时用**已有历史里的 MAC 播种** —— 否则第一轮扫描会把库里
#    每一台都当「新设备」推一遍(现在是 40 台)。
# ⚠️ 兜住异常:没配 topic、表建不出来,都不该让服务起不来。
try:
    _seeded = notifier.init(DB_PATH)
    if _seeded:
        logger.info(f"New-device alerting: seeded {_seeded} known MAC(s) from history")
    logger.info(
        "New-device alerting: %s",
        "enabled" if notifier.topic() else "no topic configured (~/.ntfy-topic), staying quiet",
    )
except Exception as _exc:
    logger.warning(f"Could not initialise new-device alerting: {_exc}")
logger.info("Database initialized")

# Check if running with sudo on macOS
if sys.platform == "darwin":
    if os.geteuid() != 0:
        logger.warning("=" * 60)
        logger.warning("⚠️  Running without sudo on macOS")
        logger.warning("For full network scanning, run: sudo python main.py")
        logger.warning("=" * 60)

app = FastAPI(title="Local Network Device Control Plane")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
class ScannerState:
    def __init__(self):
        self.devices = []
        self.previous_devices = []
        self.last_scan = None
        self.next_scan = None
        self.scanning = False
        self.scan_interval = 30  # seconds
        self.lock = threading.Lock()
        self.active_connections: Set[WebSocket] = set()

state = ScannerState()

def compare_devices(current_devices, previous_devices, scan_id: int, grace_scans=3):
    """
    Compare current scan with previous scan to detect changes.
    Uses database to track device history and categorize devices.

    Simplified categories:
    - new: Truly new device (≤3 scans)
    - regular: Seen in >70% of scans
    - occasional: Seen in 30-70% of scans
    - rare: Seen in <30% of scans
    - offline: Currently not responding (after grace period)

    Grace period: Devices aren't marked offline until they miss grace_scans consecutive scans.
    """
    # Create lookup by IP address
    prev_ips = {d['ip']: d for d in previous_devices}
    curr_ips = {d['ip']: d for d in current_devices}
    now = datetime.now()

    result = []

    # Process currently online devices
    for device in current_devices:
        ip = device['ip']
        mac = device['mac']
        hostname = device['hostname']

        # Get device history
        history = get_device_history(ip)
        vendor = get_vendor_for_mac(mac) or (history.get('vendor') if history else None)

        # Update database
        update_device(ip, mac, hostname, vendor=vendor, is_online=True)

        # Calculate category with reason (online device)
        # Pass consecutive_online for streak-based upgrades
        if history:
            recent_streak = history.get('consecutive_online', 0)
            category, reason = calculate_device_category(history, is_online=True, recent_streak=recent_streak)
        else:
            category, reason = 'new', 'no history yet'

        # Add enriched data
        device['category'] = category
        device['status'] = 'online'
        device['last_seen'] = now.isoformat()
        device['missed_scans'] = 0

        if history:
            device['first_seen'] = history['first_seen']
            device['total_scans'] = history['total_scans']
            device['scans_seen_online'] = history['scans_seen_online']
            device['appearance_rate'] = history['scans_seen_online'] / history['total_scans'] if history['total_scans'] > 0 else 0
            device['notes'] = history.get('notes', '')
            device['vendor'] = history.get('vendor') or vendor or ''
            device['os_guess'] = history.get('os_guess') or ''
            device['os_accuracy'] = history.get('os_accuracy')
            device['os_scanned_at'] = history.get('os_scanned_at')
            device['os_last_error'] = history.get('os_last_error') or ''
            device['os_last_error_at'] = history.get('os_last_error_at')
            device['last_port_scan_at'] = history.get('last_port_scan_at')
            device['last_port_scan_count'] = history.get('last_port_scan_count', 0)
            device['ssdp_server'] = history.get('ssdp_server') or ''
            device['ssdp_location'] = history.get('ssdp_location') or ''
            device['ssdp_st'] = history.get('ssdp_st') or ''
            device['ssdp_usn'] = history.get('ssdp_usn') or ''
            device['ssdp_scanned_at'] = history.get('ssdp_scanned_at')
        else:
            device['first_seen'] = now.isoformat()
            device['total_scans'] = 1
            device['scans_seen_online'] = 1
            device['appearance_rate'] = 1.0
            device['notes'] = ''
            device['vendor'] = vendor or ''
            device['os_guess'] = ''
            device['os_accuracy'] = None
            device['os_scanned_at'] = None
            device['os_last_error'] = ''
            device['os_last_error_at'] = None
            device['last_port_scan_at'] = None
            device['last_port_scan_count'] = 0
            device['ssdp_server'] = ''
            device['ssdp_location'] = ''
            device['ssdp_st'] = ''
            device['ssdp_usn'] = ''
            device['ssdp_scanned_at'] = None

        # Log categorization decision
        log_categorization(
            scan_id=scan_id,
            ip=ip,
            hostname=hostname,
            total_scans=device['total_scans'],
            scans_seen_online=device['scans_seen_online'],
            appearance_rate=device['appearance_rate'],
            category=category,
            device_status='online',
            reason=reason
        )

        logger.info(f"[CATEGORIZATION] {ip} ({hostname}): {category} | total={device['total_scans']} online={device['scans_seen_online']} rate={device['appearance_rate']:.2%} | reason: {reason}")

        result.append(device)

    # Handle devices that weren't found in current scan (offline devices)
    for ip, prev_device in prev_ips.items():
        if ip not in curr_ips:
            # Increment missed scans counter
            missed_scans = prev_device.get('missed_scans', 0) + 1

            # Update database (mark as seen but offline) only after grace period for counters
            history = get_device_history(ip)
            vendor = history.get('vendor') if history else None
            count_offline = missed_scans >= grace_scans
            update_device(
                ip,
                prev_device.get('mac', 'unknown'),
                prev_device.get('hostname', 'Unknown'),
                vendor=vendor,
                is_online=False,
                count_offline=count_offline
            )

            regular_candidate = False
            if history:
                recent_streak = history.get('consecutive_online', 0)
                regular_candidate = calculate_device_category(history, is_online=True, recent_streak=recent_streak)[0] == 'regular'

            # Show offline devices after grace period, or immediately if they are regular
            if missed_scans >= grace_scans or regular_candidate:
                offline_device = prev_device.copy()
                offline_device['status'] = 'offline'
                offline_device['missed_scans'] = missed_scans

                # Calculate category for offline device
                if history:
                    category, reason = calculate_device_category(history, is_online=False)
                    offline_device['category'] = category
                    offline_device['total_scans'] = history['total_scans']
                    offline_device['scans_seen_online'] = history['scans_seen_online']
                    offline_device['appearance_rate'] = history['scans_seen_online'] / history['total_scans'] if history['total_scans'] > 0 else 0
                    offline_device['notes'] = history.get('notes', '')
                    offline_device['vendor'] = history.get('vendor') or ''
                    offline_device['os_guess'] = history.get('os_guess') or ''
                    offline_device['os_accuracy'] = history.get('os_accuracy')
                    offline_device['os_scanned_at'] = history.get('os_scanned_at')
                    offline_device['os_last_error'] = history.get('os_last_error') or ''
                    offline_device['os_last_error_at'] = history.get('os_last_error_at')
                    offline_device['last_port_scan_at'] = history.get('last_port_scan_at')
                    offline_device['last_port_scan_count'] = history.get('last_port_scan_count', 0)
                    offline_device['ssdp_server'] = history.get('ssdp_server') or ''
                    offline_device['ssdp_location'] = history.get('ssdp_location') or ''
                    offline_device['ssdp_st'] = history.get('ssdp_st') or ''
                    offline_device['ssdp_usn'] = history.get('ssdp_usn') or ''
                    offline_device['ssdp_scanned_at'] = history.get('ssdp_scanned_at')

                    if regular_candidate and missed_scans < grace_scans:
                        reason = f"regular device offline (missed {missed_scans} scans) | {reason}"

                    # Log categorization for offline device
                    log_categorization(
                        scan_id=scan_id,
                        ip=ip,
                        hostname=prev_device.get('hostname', 'Unknown'),
                        total_scans=offline_device['total_scans'],
                        scans_seen_online=offline_device['scans_seen_online'],
                        appearance_rate=offline_device['appearance_rate'],
                        category=category,
                        device_status='offline',
                        reason=f"OFFLINE (missed {missed_scans} scans) | {reason}"
                    )

                    logger.info(f"[CATEGORIZATION] {ip} ({prev_device.get('hostname', 'Unknown')}): {category} | total={offline_device['total_scans']} online={offline_device['scans_seen_online']} rate={offline_device['appearance_rate']:.2%} | reason: {reason}")

                result.append(offline_device)
            else:
                # Keep device in list but increment missed counter
                prev_device['missed_scans'] = missed_scans
                result.append(prev_device)

    return result

# Background scanning task
async def continuous_scanner(interval: int = 30):
    """Continuously scan the network and broadcast updates"""
    logger.info(f"Starting continuous scanner (interval: {interval}s)")
    state.scan_interval = interval

    while True:
        try:
            logger.info("Performing network scan...")
            state.scanning = True

            # Notify clients that scan is starting
            if state.active_connections:
                await broadcast({
                    "type": "scan_start",
                    "message": "Starting network scan..."
                })

            # Run scan in thread pool to not block event loop
            loop = asyncio.get_event_loop()
            devices = await loop.run_in_executor(None, scan_network)

            # Record scan in database and get scan_id
            scan_id = record_scan(len(devices), scan_method="scapy")

            # Compare with previous scan to detect changes
            devices_with_status = compare_devices(devices, state.previous_devices, scan_id=scan_id)

            # 新设备告警(ntfy)。⚠️ 放在 compare_devices 之后 —— 那时才有
            #    vendor / hostname 这些富化字段。
            # ⚠️ 整段兜住:**告警失败绝不能影响扫描本身**。
            try:
                notifier.alert_new_devices(DB_PATH, devices_with_status)
            except Exception as exc:
                logger.warning(f"New-device alerting failed, scan unaffected: {exc}")

            # Count changes
            new_count = sum(1 for d in devices_with_status if d.get('device_status') == 'new')
            offline_count = sum(1 for d in devices_with_status if d.get('device_status') == 'offline')

            with state.lock:
                state.previous_devices = devices.copy()  # Store for next comparison
                state.devices = devices_with_status
                state.last_scan = datetime.now()
                state.next_scan = state.last_scan + timedelta(seconds=interval)
                state.scanning = False

            logger.info(f"Scan complete: {len(devices)} online, {new_count} new, {offline_count} offline")

            # Send progress message
            if state.active_connections:
                await broadcast({
                    "type": "scan_progress",
                    "message": f"Scan complete: {len(devices)} devices online, {new_count} new, {offline_count} offline"
                })

            # Broadcast final results to all connected WebSocket clients
            if state.active_connections:
                message = {
                    "type": "scan_update",
                    "devices": devices_with_status,
                    "count": len(devices),
                    "new_count": new_count,
                    "offline_count": offline_count,
                    "timestamp": state.last_scan.isoformat(),
                    "next_scan": state.next_scan.isoformat(),
                    "scan_interval": interval,
                    "scanning": False
                }
                await broadcast(message)

        except Exception as e:
            logger.error(f"Error in continuous scanner: {e}")
            state.scanning = False
            if state.active_connections:
                await broadcast({
                    "type": "scan_error",
                    "message": f"Scan error: {str(e)}"
                })

        # Wait for next scan
        await asyncio.sleep(interval)

async def speedtest_loop():
    """按自己的慢节奏跑测速。

    ⚠️ **和设备扫描完全分开。** 扫描 40 秒一轮、几乎不耗流量;
       测速会**把家里的上行占满将近一分钟**,同节奏跑等于把网弄卡,
       而且测出来的数也没意义。默认 6 小时一次。

    ⚠️ **放 executor 里跑。** `speedtest-cli` 是阻塞的子进程,直接 await
       会把整个事件循环钉住 —— 扫描和 WebSocket 推送会一起停。
    """
    if not speedtest_runner.available():
        return
    # 起来先等一会儿再测:开机那阵子别和别的事抢带宽
    await asyncio.sleep(120)
    while True:
        try:
            row = await asyncio.get_running_loop().run_in_executor(
                None, speedtest_runner.run_once, DB_PATH
            )
            await broadcast({"type": "speedtest", "result": row})
        except Exception as exc:
            logger.warning(f"Speed test loop error (continuing): {exc}")
        await asyncio.sleep(speedtest_runner.interval_hours() * 3600)


async def broadcast(message: dict):
    """Broadcast message to all connected WebSocket clients"""
    disconnected = set()

    for connection in list(state.active_connections):
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            disconnected.add(connection)

    # Clean up disconnected clients
    state.active_connections -= disconnected

@app.on_event("startup")
async def startup_event():
    """Start the background scanner and the speed-test loop on startup."""
    asyncio.create_task(continuous_scanner(interval=30))
    # ⚠️ speedtest_loop() was written and documented as "every 6 hours" on
    #    2026-09-27 but never scheduled here, so in three days the only rows in
    #    `speedtests` were the two manual runs. Defining the coroutine is not
    #    starting it.
    asyncio.create_task(speedtest_loop())
    logger.info("Application started - background scanner and speed-test loop running")

# ⚠️ This banner used to live at "/" — which silently shadowed the StaticFiles
#    mount, so the browser got JSON instead of the UI. An explicit route always
#    wins over a mount, and the symptom is a blank page, not an error. Moved to
#    /api so "/" belongs to the frontend.
@app.get("/api")
async def api_root():
    return {
        "message": "Local Network Device Control Plane API",
        "websocket": "/ws",
        "rest_api": "/api/devices"
    }

@app.get("/api/devices")
async def get_devices():
    """Get current device list (REST endpoint for compatibility)"""
    with state.lock:
        return {
            "success": True,
            "devices": state.devices,
            "count": len(state.devices),
            "last_scan": state.last_scan.isoformat() if state.last_scan else None,
            "scanning": state.scanning
        }

@app.get("/api/database/stats")
async def get_db_stats():
    """Get database statistics"""
    stats = get_database_stats()
    total_scans = get_total_scans()
    known_devices = get_all_known_devices()

    return {
        "success": True,
        "total_devices": stats['total_devices'],
        "total_scans": total_scans,
        "active_24h": stats['active_24h'],
        "devices": [
            {
                "ip": d['ip'],
                "hostname": d['hostname'],
                "total_scans": d['total_scans'],
                "scans_seen_online": d['scans_seen_online'],
                "appearance_rate": round(d['scans_seen_online'] / d['total_scans'] * 100, 1) if d['total_scans'] > 0 else 0,
                "category": calculate_device_category(d)[0],  # Get category from tuple
                "notes": d.get('notes', ''),
                "vendor": d.get('vendor', ''),
                "os_guess": d.get('os_guess', ''),
                "os_accuracy": d.get('os_accuracy'),
                "os_scanned_at": d.get('os_scanned_at'),
                "os_last_error": d.get('os_last_error', ''),
                "os_last_error_at": d.get('os_last_error_at'),
                "last_port_scan_at": d.get('last_port_scan_at'),
                "last_port_scan_count": d.get('last_port_scan_count', 0),
                "ssdp_server": d.get('ssdp_server', ''),
                "ssdp_location": d.get('ssdp_location', ''),
                "ssdp_st": d.get('ssdp_st', ''),
                "ssdp_usn": d.get('ssdp_usn', ''),
                "ssdp_scanned_at": d.get('ssdp_scanned_at')
            }
            for d in known_devices
        ]
    }

@app.get("/api/categorization/log")
async def get_cat_log(limit: int = 100):
    """Get categorization log for debugging"""
    try:
        log_entries = get_categorization_log(limit=limit)
        return {
            "success": True,
            "log": log_entries,
            "count": len(log_entries)
        }
    except Exception as e:
        logger.error(f"Error fetching categorization log: {e}")
        return {"success": False, "message": str(e)}

def _presence_query(fn, *args):
    conn = sqlite3.connect(DB_PATH)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


@app.get("/api/server-time")
async def server_time():
    """库里的时间都是**服务器本地时间、不带时区**(bobrasp2 是 Europe/London)。
    前端拿这个偏移把它们换成绝对时刻 —— 不换的话浏览器按自己的时区读,纽约看全部快 5 小时。"""
    return {"success": True, "offset_min": presence.server_offset_min(),
            "now": datetime.now().astimezone().isoformat()}


@app.get("/api/devices/{ip}/presence")
async def device_presence(ip: str, days: int = 14):
    """这台设备最近 days 天每小时:扫了几次、出现几次。"""
    days = max(1, min(days, 60))
    rows = await asyncio.to_thread(_presence_query, presence.hourly_presence, ip, days)
    return {"success": True, "ip": ip, "hours": rows}


@app.get("/api/presence/events")
async def presence_events(hours: int = 72, min_away_min: int = 15):
    """最近 hours 小时的来去记录(离开超过 min_away_min 分钟才算走)。"""
    hours = max(1, min(hours, 24 * 14))
    rows = await asyncio.to_thread(_presence_query, presence.recent_events, hours, min_away_min)
    return {"success": True, "events": rows, "hours": hours, "min_away_min": min_away_min}


@app.get("/api/speedtest")
async def get_speedtest(limit: int = 50):
    """最近的测速记录。⚠️ 失败的那几次也在里面 —— 只存成功的话,
    断网期看起来就是一段空白,而空白和「监控没开」长得一样。"""
    rows = speedtest_runner.history(DB_PATH, limit=limit)
    latest_ok = next((r for r in rows if r.get("ok")), None)
    return {"success": True, "latest": rows[0] if rows else None,
            "latest_ok": latest_ok, "history": rows,
            "interval_hours": speedtest_runner.interval_hours(),
            "available": speedtest_runner.available()}


@app.post("/api/speedtest/run")
async def run_speedtest_now():
    """手动测一次。⚠️ 会占满上行几十秒。"""
    row = await asyncio.get_running_loop().run_in_executor(
        None, speedtest_runner.run_once, DB_PATH
    )
    await broadcast({"type": "speedtest", "result": row})
    return {"success": bool(row.get("ok")), "result": row}


@app.post("/api/devices/{ip}/notes")
async def update_notes(ip: str, notes: dict):
    """Update notes for a device"""
    try:
        update_device_notes(ip, notes.get('notes', ''))
        return {"success": True, "message": "Notes updated"}
    except Exception as e:
        logger.error(f"Error updating notes: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/devices/{ip}/scan-ports")
async def scan_device_ports(ip: str, timeout: float = 2.5, max_workers: int = 15, retries: int = 2, service_scan: bool = False):
    """Scan ports on a specific device"""
    try:
        logger.info(
            f"Starting port scan for {ip} (timeout={timeout}s, workers={max_workers}, retries={retries}, "
            f"service_scan={service_scan})"
        )

        # Run port scan in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: scan_ports(ip, timeout=timeout, max_workers=max_workers, retries=retries)
        )

        logger.info(f"Port scan complete for {ip}: {len(results)} open ports")

        service_scan_error = None
        if service_scan and results:
            open_ports = [r['port'] for r in results]
            service_data = await loop.run_in_executor(
                None,
                lambda: scan_services(ip, open_ports)
            )
            if service_data.get("error"):
                service_scan_error = service_data["error"]
                history = get_device_history(ip)
                hostname = history.get('hostname') if history else ''
                log_scan_event(ip, hostname or '', "service_scan", f"{ip}: {service_scan_error}")
            else:
                services = service_data.get("services", {})
                for result in results:
                    service_info = services.get(result["port"])
                    if service_info:
                        result["service"] = service_info.get("service") or result.get("service")
                        result["details"] = service_info.get("details") or result.get("details")

        # Check if this device is running Pi-hole
        pihole_info = None
        if results:
            open_port_numbers = [r['port'] for r in results]
            pihole_info = await loop.run_in_executor(
                None,
                lambda: check_if_pihole(ip, open_port_numbers)
            )

            if pihole_info:
                logger.info(f"✓ Pi-hole detected on {ip}: {pihole_info['admin_url']}")

        # Save results to database (including Pi-hole info)
        save_port_scan_results(ip, results, pihole_info)

        return {
            "success": True,
            "ip": ip,
            "open_ports": len(results),
            "ports": results,
            "pihole": pihole_info,
            "config": {
                "timeout": timeout,
                "max_workers": max_workers,
                "retries": retries,
                "service_scan": service_scan
            },
            "service_scan_error": service_scan_error
        }
    except Exception as e:
        logger.error(f"Error scanning ports for {ip}: {e}")
        history = get_device_history(ip)
        hostname = history.get('hostname') if history else ''
        log_scan_event(ip, hostname or '', "port_scan", f"{ip}: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/devices/{ip}/scan-os")
async def scan_device_os(ip: str, timeout: int = 30):
    """Scan OS details for a specific device (requires nmap and sudo)"""
    try:
        logger.info(f"Starting OS scan for {ip} (timeout={timeout}s)")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: scan_os(ip, timeout_seconds=timeout))

        if result.get("error"):
            error_message = f"{ip}: {result['error']}"
            update_device_os_error(ip, error_message)
            history = get_device_history(ip)
            hostname = history.get('hostname') if history else ''
            log_scan_event(ip, hostname or '', "os_scan", error_message)
            return {"success": False, "message": error_message}

        os_guess = result.get("os_guess")
        os_accuracy = result.get("os_accuracy")
        if os_guess:
            update_device_os(ip, os_guess, os_accuracy)

        return {
            "success": True,
            "ip": ip,
            "os_guess": os_guess,
            "os_accuracy": os_accuracy,
            "os_scanned_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error scanning OS for {ip}: {e}")
        history = get_device_history(ip)
        hostname = history.get('hostname') if history else ''
        log_scan_event(ip, hostname or '', "os_scan", f"{ip}: {e}")
        return {"success": False, "message": str(e)}

@app.get("/api/devices/{ip}/ports")
async def get_device_ports(ip: str):
    """Get latest port scan results for a device"""
    try:
        scan_data = get_latest_port_scan(ip)

        if scan_data:
            return {
                "success": True,
                "ip": ip,
                "scan_time": scan_data['scan_time'],
                "ports": scan_data['ports']
            }
        else:
            return {
                "success": True,
                "ip": ip,
                "scan_time": None,
                "ports": []
            }
    except Exception as e:
        logger.error(f"Error fetching port scan for {ip}: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/devices/{ip}/discover-ssdp")
async def discover_device_ssdp(ip: str, timeout: float = 2.0):
    """Discover SSDP/UPnP info for a device"""
    try:
        logger.info(f"Starting SSDP discovery for {ip} (timeout={timeout}s)")
        loop = asyncio.get_event_loop()
        responses = await loop.run_in_executor(None, lambda: discover_ssdp(ip, timeout))
        info = responses.get(ip)
        if info:
            update_device_ssdp(ip, info)
            return {"success": True, "ip": ip, "ssdp": info}
        message = f"{ip}: No SSDP response received."
        history = get_device_history(ip)
        hostname = history.get('hostname') if history else ''
        log_scan_event(ip, hostname or '', "ssdp", message)
        return {"success": False, "message": message}
    except Exception as e:
        logger.error(f"Error discovering SSDP for {ip}: {e}")
        history = get_device_history(ip)
        hostname = history.get('hostname') if history else ''
        log_scan_event(ip, hostname or '', "ssdp", f"{ip}: {e}")
        return {"success": False, "message": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time device updates"""
    await websocket.accept()
    state.active_connections.add(websocket)
    logger.info(f"WebSocket client connected (total: {len(state.active_connections)})")

    try:
        # Send initial state
        with state.lock:
            await websocket.send_json({
                "type": "initial_state",
                "devices": state.devices,
                "count": len(state.devices),
                "timestamp": state.last_scan.isoformat() if state.last_scan else None,
                "next_scan": state.next_scan.isoformat() if state.next_scan else None,
                "scan_interval": state.scan_interval,
                "scanning": state.scanning
            })

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle client requests
            if message.get("type") == "scan_now":
                logger.info("Client requested immediate scan")

                # Notify scan starting
                await broadcast({
                    "type": "scan_start",
                    "message": "Manual scan requested..."
                })

                # Trigger immediate scan
                loop = asyncio.get_event_loop()
                devices = await loop.run_in_executor(None, scan_network)

                # Record scan in database and get scan_id
                scan_id = record_scan(len(devices), scan_method="scapy")

                # Compare with previous scan
                devices_with_status = compare_devices(devices, state.previous_devices, scan_id=scan_id)
                new_count = sum(1 for d in devices_with_status if d.get('device_status') == 'new')
                offline_count = sum(1 for d in devices_with_status if d.get('device_status') == 'offline')

                with state.lock:
                    state.previous_devices = devices.copy()
                    state.devices = devices_with_status
                    state.last_scan = datetime.now()
                    # Note: Don't update next_scan here - background scanner controls schedule

                # Send progress message
                await broadcast({
                    "type": "scan_progress",
                    "message": f"Manual scan complete: {len(devices)} online, {new_count} new, {offline_count} offline"
                })

                # Broadcast update
                await broadcast({
                    "type": "scan_update",
                    "devices": devices_with_status,
                    "count": len(devices),
                    "new_count": new_count,
                    "offline_count": offline_count,
                    "timestamp": state.last_scan.isoformat(),
                    "next_scan": state.next_scan.isoformat() if state.next_scan else None,
                    "scan_interval": state.scan_interval,
                    "scanning": False
                })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        state.active_connections.discard(websocket)
        logger.info(f"WebSocket client removed (remaining: {len(state.active_connections)})")

# --- Serve the built frontend from this same process -------------------------
#
# Why here and not a separate Vite dev server: behind network.dorafmon.com the
# page and the API must be same-origin, otherwise the browser resolves
# "localhost:8000" against *itself*. One process also means one LaunchAgent and
# no dev server exposed to the tunnel.
#
# Mounted last, so every API route and /ws above still wins. html=True makes the
# SPA fall back to index.html for unknown paths.
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
    logger.info(f"Serving built frontend from {_DIST}")
else:
    logger.warning(
        f"No built frontend at {_DIST} — run `npm run build` in frontend/. "
        "The API still works; only the UI is missing."
    )

if __name__ == "__main__":
    # Defaults to loopback: the intended ingress is a Cloudflare tunnel, and on a
    # host where the tunnel runs locally there is no reason to listen on the LAN.
    # LNA_HOST=0.0.0.0 is for the case where the tunnel runs on a *different*
    # machine and has to reach this one across the LAN — set it in the unit file,
    # not here, so the safe default stays the default.
    host = os.environ.get("LNA_HOST", "127.0.0.1")
    port = int(os.environ.get("LNA_PORT", "8000"))
    logger.info(f"Listening on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
