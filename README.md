# Local Network Device Control Plane

A real-time network device monitoring and management application that scans your local network and provides a clean, minimalist interface for tracking devices.

## Features

### Core Functionality
- **Real-time Network Scanning**: Continuous ARP scanning using Scapy (pure Python, no subprocess)
- **WebSocket Push Architecture**: Real-time updates via WebSocket, no polling
- **Device Persistence**: SQLite database tracks device history and appearance patterns
- **Smart Categorization**: Automatically categorizes devices based on frequency:
  - **NEW**: First time seen (< 5 scans)
  - **REGULAR**: Seen in >70% of scans (reliable devices)
  - **OCCASIONAL**: Seen in 30-70% of scans
  - **RARE**: Seen in <30% of scans (infrequent visitors)
- **Grace Period System**: Devices aren't marked offline until missing 3 consecutive scans (handles power-saving modes)
- **Hostname Resolution**: Automatic reverse DNS lookup for device names
- **Manual Notes**: Add custom notes to any device
- **Debug Panel**: View database statistics and export CSV for analysis

### User Interface
- **Minimalist Design**: Inspired by usgraphics.com - clean, typographic, functional
- **Color-Coded Devices**:
  - 🟢 Green: New devices just discovered
  - 🔵 Blue: Regular devices (frequently seen)
  - 🟡 Amber: Rare devices (infrequent)
  - 🔴 Gray: Offline devices
  - Blue-gray: Regular devices currently offline
- **Tabbed Interface**:
  - **Devices Tab**: Live device table with inline note editing
  - **Debug Tab**: Database statistics, device history, CSV export
- **Status Panel**: Connection status, device count, scan countdown, scan log, color legend
- **Live Scan Progress**: Visual countdown timer and rolling log of scan events

## Architecture

### Backend (FastAPI + Python)
```
backend/
├── main.py              # FastAPI app, WebSocket server, continuous scanner
├── network_scanner.py   # Scapy-based ARP scanning, hostname resolution
├── database.py          # SQLite database operations, device categorization
├── devices.db          # SQLite database (auto-created)
├── requirements.txt    # Python dependencies
├── dev.sh             # Development mode with auto-restart
├── dev-watch.py       # Auto-restart script using watchdog
├── start-with-sudo.sh # Production start script
└── setup-passwordless-sudo.sh # One-time sudo setup
```

**Key Components**:
- **Continuous Scanner**: Background asyncio task scans every 30 seconds
- **Device Comparison**: Tracks device state changes (new, offline, existing)
- **Database Layer**: Persistent storage with automatic migrations
- **WebSocket Broadcasts**: Real-time updates to all connected clients

### Frontend (React + Vite)
```
frontend/
├── src/
│   ├── App.jsx        # Main component with tabs, WebSocket client
│   ├── App.css        # Minimalist USGC-inspired styles
│   └── main.jsx       # React entry point
├── index.html
└── package.json
```

**Key Features**:
- WebSocket connection with auto-reconnect
- Tabbed interface (Devices / Debug)
- Inline note editing (click to edit, Enter to save)
- Real-time countdown timer
- CSV export functionality

## Installation

### Prerequisites
- Python 3.8+ (tested on Python 3.13)
- Node.js 18+ (for frontend)
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- sudo access (for network scanning)

### Backend Setup

1. **Install dependencies**:
```bash
cd backend
uv venv
source .venv/bin/activate  # On macOS/Linux
uv pip install -r requirements.txt
```

2. **Configure passwordless sudo** (recommended, one-time):
```bash
./setup-passwordless-sudo.sh
```

This allows the backend to run network scans without password prompts.

3. **Start the backend**:

**Production mode**:
```bash
./start-with-sudo.sh
```

**Development mode** (auto-restart on file changes):
```bash
sudo ./dev.sh
```

The backend will run on `http://localhost:8000`

### Frontend Setup

1. **Install dependencies**:
```bash
cd frontend
npm install
```

2. **Start the development server**:
```bash
npm run dev
```

The frontend will run on `http://localhost:5173`

## Usage

1. Start the backend with sudo (required for network scanning)
2. Start the frontend
3. Open `http://localhost:5173` in your browser
4. The app will automatically connect via WebSocket and start scanning

### Adding Notes to Devices

1. Go to the **Devices** tab
2. Click on any device's **Notes** field
3. Type your note (e.g., "Bob's iPhone", "Living Room TV")
4. Press **Enter** to save (or **Escape** to cancel)
5. Notes are persisted in the database

### Exporting Device Data

1. Go to the **Debug** tab
2. Click **Copy CSV** to copy to clipboard
3. Or click **Download CSV** to save as a file
4. CSV includes: IP, Hostname, Total Scans, Scans Online, Appearance Rate, Category, Notes

## Database Schema

### `devices` Table
```sql
- id: INTEGER PRIMARY KEY
- ip: TEXT UNIQUE (device IP address)
- mac: TEXT (MAC address)
- hostname: TEXT (resolved hostname)
- notes: TEXT (user-added notes)
- first_seen: TEXT (ISO timestamp)
- last_seen: TEXT (ISO timestamp)
- last_seen_online: TEXT (ISO timestamp)
- total_scans: INTEGER (total scans device was tracked)
- scans_seen_online: INTEGER (scans where device responded)
- scans_seen_offline: INTEGER (scans where device didn't respond)
- consecutive_offline: INTEGER (current offline streak)
- created_at: TEXT (ISO timestamp)
- updated_at: TEXT (ISO timestamp)
```

### `scans` Table
```sql
- id: INTEGER PRIMARY KEY
- scan_time: TEXT (ISO timestamp)
- devices_found: INTEGER (number of devices)
- scan_method: TEXT (scanning method used)
```

## API Endpoints

### REST API
- `GET /` - API info
- `GET /api/devices` - Get current device list (REST endpoint)
- `GET /api/database/stats` - Get database statistics and device history
- `POST /api/devices/{ip}/notes` - Update notes for a device

### WebSocket
- `WS /ws` - Real-time device updates

**WebSocket Messages (Server → Client)**:
```javascript
{
  type: "initial_state",  // Initial connection
  devices: [...],
  count: 10,
  timestamp: "2025-12-28T...",
  next_scan: "2025-12-28T...",
  scan_interval: 30,
  scanning: false
}

{
  type: "scan_start",  // Scan beginning
  message: "Starting network scan..."
}

{
  type: "scan_progress",  // Scan progress
  message: "Scan complete: 10 devices online, 1 new, 0 offline"
}

{
  type: "scan_update",  // Scan results
  devices: [...],
  count: 10,
  new_count: 1,
  offline_count: 0,
  timestamp: "...",
  next_scan: "...",
  scan_interval: 30,
  scanning: false
}
```

**WebSocket Messages (Client → Server)**:
```javascript
{
  type: "scan_now"  // Request immediate scan
}
```

## Device Categorization Logic

Devices are categorized based on their appearance rate over time:

```python
if total_scans < 5:
    category = 'new'  # Need more data
elif appearance_rate >= 0.7:
    category = 'regular'  # Seen in >70% of scans
elif appearance_rate >= 0.3:
    category = 'occasional'  # Seen in 30-70% of scans
else:
    category = 'rare'  # Seen in <30% of scans
```

**Appearance Rate** = `scans_seen_online / total_scans`

## Color Coding

### Badges (Status)
- **NEW** (green) - Device just appeared in current scan
- **OFFLINE** (red) - Device hasn't responded for 3+ scans
- **REGULAR** (blue) - Frequently seen device (>70% appearance rate)
- **RARE** (amber) - Infrequently seen device (<30% appearance rate)

### Row Background Colors
- **Light Green** - New devices (status)
- **Light Blue** - Regular devices (category)
- **Light Yellow** - Rare devices (category)
- **Light Gray** - Offline devices (status)
- **Blue-Gray** - Regular devices that are offline

## Configuration

### Scan Settings
Edit `main.py` to change scan parameters:
```python
# Scan interval (seconds)
asyncio.create_task(continuous_scanner(interval=30))

# Grace period (missed scans before marking offline)
devices_with_status = compare_devices(devices, state.previous_devices, grace_scans=3)
```

### Scapy Scan Tuning
Edit `network_scanner.py`:
```python
def scan_with_scapy(timeout: int = 5, retry: int = 3):
    # timeout: seconds to wait for responses
    # retry: number of retries for unanswered requests
```

## Troubleshooting

### "Permission denied" errors
Network scanning requires root/sudo access. Use `sudo ./dev.sh` or `./start-with-sudo.sh`

### Passwordless sudo not working
1. Check that `/etc/sudoers.d/local-network-scanner` exists
2. Verify the paths match: `sudo cat /etc/sudoers.d/local-network-scanner`
3. Re-run `./setup-passwordless-sudo.sh`

### Devices showing as "Unknown"
- Some devices don't respond to reverse DNS lookups
- Try adding custom notes to identify them

### Devices flickering online/offline
- Increase grace period in `main.py`: `grace_scans=3` → `grace_scans=5`
- Increase scan timeout in `network_scanner.py`: `timeout=5` → `timeout=10`

### Database corruption
Delete and recreate:
```bash
rm backend/devices.db
# Restart backend - database will be recreated
```

## Development

### Auto-restart on changes
```bash
cd backend
sudo ./dev.sh
```

Uses Python watchdog to automatically restart the server when `.py` files change.

### Database inspection
```bash
# View device statistics
sqlite3 backend/devices.db "SELECT ip, hostname, total_scans, scans_seen_online FROM devices;"

# View scan history
sqlite3 backend/devices.db "SELECT * FROM scans ORDER BY scan_time DESC LIMIT 10;"
```

### Frontend development
```bash
cd frontend
npm run dev  # Hot reload enabled
```

## Tech Stack

**Backend**:
- FastAPI - Modern async web framework
- Uvicorn - ASGI server
- Scapy - Pure Python packet manipulation
- SQLite - Embedded database
- Watchdog - File monitoring for dev mode

**Frontend**:
- React 18 - UI framework
- Vite - Build tool and dev server
- WebSocket API - Real-time communication

## Security Considerations

- **Sudo Access**: Required for raw socket access (ARP scanning)
- **Local Network Only**: No external network access
- **No Authentication**: Designed for trusted local networks
- **Passwordless Sudo**: Configure carefully, scoped to specific commands

## Performance

- **Scan Time**: ~3-5 seconds per scan (depends on network size)
- **Memory**: ~50MB backend, ~30MB frontend
- **Database**: ~20-50KB per 100 devices
- **Network Load**: Minimal (single broadcast ARP per scan)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Update CHANGELOG.md
6. Submit a pull request
