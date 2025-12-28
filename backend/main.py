from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from network_scanner import scan_network
from port_scanner import scan_ports
from pi_hole_detector import check_if_pihole
from database import (
    init_database, update_device, increment_total_scans,
    get_device_history, get_all_known_devices, calculate_device_category,
    record_scan, get_database_stats, get_total_scans, update_device_notes,
    log_categorization, get_categorization_log, save_port_scan_results,
    get_latest_port_scan
)
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
    # Increment total scan counter for all known devices
    increment_total_scans()

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

        # Update database
        update_device(ip, mac, hostname, is_online=True)

        # Get device history
        history = get_device_history(ip)

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
        else:
            device['first_seen'] = now.isoformat()
            device['total_scans'] = 1
            device['scans_seen_online'] = 1
            device['appearance_rate'] = 1.0
            device['notes'] = ''

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
            # Update database (mark as seen but offline)
            update_device(
                ip,
                prev_device.get('mac', 'unknown'),
                prev_device.get('hostname', 'Unknown'),
                is_online=False
            )

            # Get updated history
            history = get_device_history(ip)

            # Increment missed scans counter
            missed_scans = prev_device.get('missed_scans', 0) + 1

            # Only show offline devices after grace period
            if missed_scans >= grace_scans:
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

async def broadcast(message: dict):
    """Broadcast message to all connected WebSocket clients"""
    disconnected = set()

    for connection in state.active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            disconnected.add(connection)

    # Clean up disconnected clients
    state.active_connections -= disconnected

@app.on_event("startup")
async def startup_event():
    """Start background scanner on startup"""
    asyncio.create_task(continuous_scanner(interval=30))
    logger.info("Application started - background scanner running")

@app.get("/")
async def root():
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
                "notes": d.get('notes', '')
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
async def scan_device_ports(ip: str, timeout: float = 2.0, max_workers: int = 20):
    """Scan ports on a specific device"""
    try:
        logger.info(f"Starting port scan for {ip} (timeout={timeout}s, workers={max_workers})")

        # Run port scan in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: scan_ports(ip, timeout=timeout, max_workers=max_workers)
        )

        logger.info(f"Port scan complete for {ip}: {len(results)} open ports")

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
        if results:
            save_port_scan_results(ip, results, pihole_info)

        return {
            "success": True,
            "ip": ip,
            "open_ports": len(results),
            "ports": results,
            "pihole": pihole_info,
            "config": {
                "timeout": timeout,
                "max_workers": max_workers
            }
        }
    except Exception as e:
        logger.error(f"Error scanning ports for {ip}: {e}")
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
