# WebSocket Push-Based Architecture

## Overview

The application has been upgraded from a **request-reply** polling architecture to a **push-based WebSocket** architecture with continuous background scanning.

## Architecture Comparison

### Before (Request-Reply)
```
Client                          Server
  |                               |
  |------- GET /api/devices ----->|
  |                               | (scan network)
  |<------ devices JSON ----------|
  |                               |
  | (wait)                        |
  | (user clicks refresh)         |
  |------- GET /api/devices ----->|
  |                               | (scan network again)
  |<------ devices JSON ----------|
```

**Issues:**
- Client must poll repeatedly
- Network scanned on every request (inefficient)
- No real-time updates
- Higher latency

### After (WebSocket Push)
```
Client                          Server
  |                               |
  |------- WS Connect ----------->|
  |<------ initial_state ---------|
  |                               |
  |                               | [Background Thread]
  |                               | └─> scan every 30s
  |<------ scan_update -----------|  (push to all clients)
  |                               |
  |                               | [Background Thread]
  |<------ scan_update -----------|  (automatic push)
  |                               |
  | (user clicks scan now)        |
  |------- scan_now ------------->|
  |                               | (immediate scan)
  |<------ scan_update -----------| (push result)
```

**Benefits:**
- ✅ Real-time updates pushed to clients
- ✅ Continuous scanning in background
- ✅ Efficient: scan once, broadcast to all clients
- ✅ Low latency updates
- ✅ Auto-reconnection on disconnect

## Backend Implementation

### Key Components

1. **ScannerState Class**
   - Manages shared state (devices, connections)
   - Thread-safe with locks
   - Tracks all active WebSocket connections

2. **Background Scanner Task**
   ```python
   async def continuous_scanner(interval: int = 30):
       while True:
           devices = await scan_network()
           await broadcast(devices)
           await asyncio.sleep(interval)
   ```
   - Runs continuously every 30 seconds
   - Executes in thread pool to avoid blocking
   - Broadcasts to all connected clients

3. **WebSocket Endpoint** (`/ws`)
   - Accepts WebSocket connections
   - Sends initial state on connect
   - Handles client requests (`scan_now`)
   - Auto-cleanup on disconnect

4. **Broadcast Function**
   ```python
   async def broadcast(message: dict):
       for connection in active_connections:
           await connection.send_json(message)
   ```
   - Pushes updates to all clients simultaneously
   - Handles disconnected clients gracefully

### Message Types

**Server → Client:**
- `initial_state` - Sent when client first connects
- `scan_update` - Sent when new scan completes

**Client → Server:**
- `scan_now` - Request immediate scan

### REST API Compatibility

The REST endpoint `/api/devices` is still available for:
- Debugging
- Legacy clients
- One-off requests

## Frontend Implementation

### Key Components

1. **WebSocket Connection**
   ```javascript
   const ws = new WebSocket('ws://localhost:8000/ws')
   ws.onmessage = (event) => {
       const message = JSON.parse(event.data)
       setDevices(message.devices)
   }
   ```

2. **Auto-Reconnection**
   - Automatically reconnects after 3 seconds on disconnect
   - Shows "Connecting..." status to user
   - Resumes normal operation when reconnected

3. **Manual Scan Trigger**
   ```javascript
   const scanNow = () => {
       ws.send(JSON.stringify({ type: 'scan_now' }))
   }
   ```

### State Management

- `devices` - Current device list
- `connected` - WebSocket connection status
- `loading` - Scan in progress
- `lastUpdate` - Timestamp of last scan

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Backend                      │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Background Task (asyncio)                       │  │
│  │  ├─> scan_network() every 30s                    │  │
│  │  ├─> Update ScannerState                         │  │
│  │  └─> broadcast() to all WebSocket clients        │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  ScannerState (Thread-Safe)                      │  │
│  │  ├─> devices: List[Dict]                         │  │
│  │  ├─> last_scan: datetime                         │  │
│  │  ├─> scanning: bool                              │  │
│  │  └─> active_connections: Set[WebSocket]          │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  WebSocket Endpoint (/ws)                        │  │
│  │  ├─> Accept connections                          │  │
│  │  ├─> Send initial_state                          │  │
│  │  ├─> Handle scan_now requests                    │  │
│  │  └─> Cleanup on disconnect                       │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │ WebSocket (ws://)
                      │ Full Duplex
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   React Frontend                        │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  WebSocket Client                                │  │
│  │  ├─> connectWebSocket()                          │  │
│  │  ├─> ws.onmessage → update state                 │  │
│  │  ├─> ws.onclose → auto-reconnect                 │  │
│  │  └─> scanNow() → send scan_now message           │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  React State                                     │  │
│  │  ├─> devices (from WebSocket)                    │  │
│  │  ├─> connected (connection status)               │  │
│  │  └─> lastUpdate (timestamp)                      │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  UI Render                                       │  │
│  │  └─> Table with real-time device updates         │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Configuration

### Backend Settings

- **Scan Interval**: 30 seconds (configurable in `continuous_scanner()`)
- **Thread Pool**: Uses asyncio executor for network scans
- **Concurrency**: Supports multiple WebSocket clients

### Frontend Settings

- **Reconnect Delay**: 3 seconds
- **WebSocket URL**: `ws://localhost:8000/ws`

## Performance Characteristics

| Metric | Before | After |
|--------|--------|-------|
| Update Latency | ~1-2s (user click + scan) | <100ms (push) |
| Network Scans | On-demand only | Continuous (30s) |
| Server Load | Spike per request | Steady background |
| Multiple Clients | N scans for N clients | 1 scan for N clients |
| Real-time Updates | ❌ No | ✅ Yes |

## Error Handling

1. **WebSocket Disconnect**
   - Frontend auto-reconnects after 3s
   - Backend cleans up dead connections

2. **Scan Errors**
   - Logged but don't crash the background task
   - Next scan continues normally

3. **Multiple Clients**
   - Broadcast failures don't affect other clients
   - Dead connections removed automatically

## Security Considerations

- WebSocket origin validated by CORS middleware
- No authentication (local network tool)
- Same security model as REST API

## Future Enhancements

1. **Device Change Detection**
   - Only push updates when devices change
   - Reduce unnecessary updates

2. **Configurable Scan Interval**
   - Allow clients to request different intervals
   - Adaptive scanning based on network activity

3. **Device History**
   - Track device online/offline events
   - Show last seen timestamps

4. **Filtering & Search**
   - Client-side filtering of device list
   - Search by IP, MAC, or hostname

5. **Multiple Network Support**
   - Scan multiple subnets
   - Switch between networks
