from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from network_scanner import scan_network
from database import (
    init_database, update_device, increment_total_scans,
    get_device_history, get_all_known_devices, calculate_device_category,
    record_scan, get_database_stats, get_total_scans, update_device_notes
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

def compare_devices(current_devices, previous_devices, grace_scans=3):
    """
    Compare current scan with previous scan to detect changes.
    Uses database to track device history and categorize devices.

    Device categories based on history:
    - new: First time seeing this device (< 5 scans)
    - regular: Seen in >70% of scans (frequent device)
    - occasional: Seen in 30-70% of scans
    - rare: Seen in <30% of scans

    Device status:
    - online: Currently responding to scans
    - offline: Not responding (after grace period)

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

        # Calculate category
        category = calculate_device_category(history) if history else 'new'

        # Determine device_status (for UI badge/highlighting)
        if ip not in prev_ips:
            device_status = 'new'  # Just appeared
        else:
            device_status = 'existing'

        # Add enriched data
        device['device_status'] = device_status
        device['device_category'] = category
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
                offline_device['device_status'] = 'offline'
                offline_device['status'] = 'offline'
                offline_device['missed_scans'] = missed_scans

                # Calculate category based on history
                if history:
                    category = calculate_device_category(history)
                    offline_device['device_category'] = category
                    offline_device['total_scans'] = history['total_scans']
                    offline_device['scans_seen_online'] = history['scans_seen_online']
                    offline_device['appearance_rate'] = history['scans_seen_online'] / history['total_scans'] if history['total_scans'] > 0 else 0
                    offline_device['notes'] = history.get('notes', '')

                result.append(offline_device)
            else:
                # Keep device as "existing" but increment missed counter
                prev_device['missed_scans'] = missed_scans
                prev_device['device_status'] = 'existing'
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

            # Record scan in database
            record_scan(len(devices), scan_method="scapy")

            # Compare with previous scan to detect changes
            devices_with_status = compare_devices(devices, state.previous_devices)

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
                "category": calculate_device_category(d),
                "notes": d.get('notes', '')
            }
            for d in known_devices
        ]
    }

@app.post("/api/devices/{ip}/notes")
async def update_notes(ip: str, notes: dict):
    """Update notes for a device"""
    try:
        update_device_notes(ip, notes.get('notes', ''))
        return {"success": True, "message": "Notes updated"}
    except Exception as e:
        logger.error(f"Error updating notes: {e}")
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

                # Record scan in database
                record_scan(len(devices), scan_method="scapy")

                # Compare with previous scan
                devices_with_status = compare_devices(devices, state.previous_devices)
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
