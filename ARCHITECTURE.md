# Architecture Documentation

## System Overview

The Local Network Device Control Plane is a full-stack web application designed to discover, monitor, and manage devices on a local area network (LAN). The system follows a client-server architecture with a clear separation between the frontend presentation layer and the backend business logic.

```
┌─────────────────────────────────────────────────────────────┐
│                        User Browser                         │
│                     (http://localhost:5173)                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            │ HTTP/REST API
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                      React Frontend                         │
│                         (Vite)                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  App.jsx - Main Component                          │   │
│  │  - Device state management (useState)              │   │
│  │  - API communication (fetch)                       │   │
│  │  - UI rendering                                    │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            │ fetch('http://localhost:8000/api/devices')
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    FastAPI Backend                          │
│                  (http://localhost:8000)                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  main.py - API Server                              │   │
│  │  - REST endpoints                                  │   │
│  │  - CORS middleware                                 │   │
│  │  - Request/Response handling                       │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │  network_scanner.py - Network Discovery            │   │
│  │  - Scapy ARP scanning                              │   │
│  │  - System ARP cache reading                        │   │
│  │  - Device data aggregation                         │   │
│  └──────────────────────┬──────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             │ ARP Requests/System Commands
                             │
┌────────────────────────────▼────────────────────────────────┐
│                     Local Network (LAN)                     │
│                                                             │
│  [Router] ←→ [Device 1] ←→ [Device 2] ←→ [Device N]       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Component Architecture

### Frontend Layer (React + Vite)

**Technology Stack:**
- React 18.x - UI framework
- Vite - Build tool and development server
- Modern ES6+ JavaScript
- CSS3 for styling

**Key Components:**

1. **App.jsx** (Main Component)
   - **State Management:**
     - `devices` - Array of discovered network devices
     - `loading` - Boolean for loading state
     - `error` - Error message state
     - `lastUpdate` - Timestamp of last scan

   - **Core Functions:**
     - `fetchDevices()` - Async function to call backend API
     - `useEffect()` - Triggers initial device scan on mount

   - **UI Sections:**
     - Header - App title and description
     - Controls - Refresh button and last update time
     - Error Banner - Displays errors if any
     - Loading State - Shows spinner during scan
     - Device Grid - Card-based layout of discovered devices

2. **App.css** (Styling)
   - Responsive grid layout
   - Card-based device presentation
   - Loading animations
   - Hover effects and transitions
   - Mobile-responsive design

**Data Flow (Frontend):**
```
User Action → fetchDevices() → fetch API → Update State → Re-render UI
     ↑                                                         │
     └─────────────── User sees updated devices ──────────────┘
```

### Backend Layer (FastAPI + Python)

**Technology Stack:**
- FastAPI - Modern Python web framework
- Uvicorn - ASGI server
- Scapy - Network packet manipulation
- Python 3.8+ standard library

**Key Modules:**

1. **main.py** (API Server)

   **Endpoints:**
   - `GET /` - Root endpoint, returns API info
   - `GET /api/devices` - Returns list of network devices

   **Middleware:**
   - CORS - Allows cross-origin requests from frontend
     - Configured for localhost:3000 and localhost:5173
     - Allows all methods and headers

   **Response Format:**
   ```json
   {
     "success": true/false,
     "devices": [...],
     "count": number,
     "error": "error message if any"
   }
   ```

2. **network_scanner.py** (Network Discovery)

   **Functions:**

   - `get_local_ip()` - Determines the machine's local IP address
     - Uses socket connection to external DNS (8.8.8.8)
     - No actual data sent, just determines routing

   - `get_network_prefix(ip)` - Calculates network CIDR
     - Converts IP to /24 subnet (e.g., 192.168.1.0/24)

   - `scan_with_scapy()` - Active network scanning
     - Creates ARP request packets
     - Broadcasts to all hosts in subnet
     - Collects responses with IP/MAC pairs
     - More comprehensive but requires network access

   - `scan_with_arp()` - Passive scanning (fallback)
     - Reads system's ARP cache
     - Platform-specific parsing (macOS, Linux, Windows)
     - Faster but only finds recently communicated devices

   - `scan_network()` - Main orchestrator
     - Tries Scapy first for comprehensive results
     - Falls back to ARP cache if Scapy fails
     - Adds local machine info
     - Returns unified device list

**Device Data Model:**
```python
{
    "ip": "192.168.1.100",
    "mac": "aa:bb:cc:dd:ee:ff",
    "hostname": "device-name",
    "status": "online"
}
```

### Network Discovery Mechanism

**Two-Tier Scanning Strategy:**

1. **Primary: Scapy Active Scanning**
   ```
   Application → Scapy → ARP Request → Broadcast (ff:ff:ff:ff:ff:ff)
                                              ↓
   Devices receive request ← Network ← All devices on subnet
                                              ↓
   Application ← Scapy ← ARP Replies ← Active devices respond
   ```

   **Pros:**
   - Discovers all active devices
   - Real-time network state
   - More comprehensive

   **Cons:**
   - Requires network permissions
   - May need elevated privileges
   - Slower (3-second timeout)

2. **Fallback: ARP Cache Reading**
   ```
   Application → subprocess → arp command → System ARP cache
                                                    ↓
   Application ← parsed data ← stdout ← Cache entries
   ```

   **Pros:**
   - No special permissions needed
   - Very fast
   - Works on all platforms

   **Cons:**
   - Only shows recently contacted devices
   - May miss devices that haven't communicated
   - Cache can be stale

### Communication Protocol

**API Request Flow:**
```
1. User clicks "Refresh" or page loads
   ↓
2. Frontend: fetchDevices() called
   ↓
3. HTTP GET → http://localhost:8000/api/devices
   ↓
4. Backend: FastAPI receives request
   ↓
5. Backend: Calls scan_network()
   ↓
6. Scanner: Attempts Scapy scan
   ↓
7. Scanner: Falls back to ARP if needed
   ↓
8. Scanner: Returns device list
   ↓
9. Backend: Formats JSON response
   ↓
10. Frontend: Receives response
   ↓
11. Frontend: Updates React state
   ↓
12. React: Re-renders UI with new data
```

**Error Handling:**
- Network errors caught and displayed to user
- Backend errors returned in response
- Graceful degradation (Scapy → ARP → empty list)

## Deployment Architecture

### Development Environment
```
Terminal 1: Backend Server (Port 8000)
  └─ uvicorn → FastAPI → network_scanner

Terminal 2: Frontend Dev Server (Port 5173)
  └─ Vite → React → Hot Module Replacement

OR

Single Terminal: start.sh
  ├─ Backend (background process)
  └─ Frontend (background process)
```

### Virtual Environment Strategy
- **Backend**: Python venv managed by `uv`
  - Isolated dependencies
  - Fast installation with uv
  - Located at `backend/.venv/`

- **Frontend**: Node.js packages
  - Managed by npm
  - Located at `frontend/node_modules/`

## Data Flow Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│   User   │────▶│ React UI │────▶│  FastAPI │────▶│ Network  │
└──────────┘     └──────────┘     └──────────┘     │ Scanner  │
     ▲                 ▲                 ▲          └────┬─────┘
     │                 │                 │               │
     │                 │                 │               ▼
     │                 │                 │          ┌─────────┐
     │                 │                 └──────────│  Scapy  │
     │                 │                            └────┬────┘
     │                 │                                 │
     │                 │                                 ▼
     │                 │                            ┌─────────┐
     │                 └────────────────────────────│   ARP   │
     │                                              └────┬────┘
     │                                                   │
     │                                                   ▼
     └───────────────────────────────────────────  ┌─────────┐
                                                    │   LAN   │
                                                    └─────────┘
```

## Security Considerations

1. **Network Permissions**
   - Scapy may require elevated permissions (sudo/admin)
   - Application gracefully degrades if permissions lacking
   - Only scans local network (no external access)

2. **CORS Policy**
   - Configured for localhost only
   - Prevents unauthorized cross-origin requests
   - Safe for local development

3. **Data Privacy**
   - No data persistence
   - All scans are real-time
   - No external data transmission
   - Information stays on local network

4. **Input Validation**
   - Backend validates all responses
   - Frontend handles errors gracefully
   - No user input directly executed

## Scalability & Performance

**Current Limitations:**
- Single-threaded scanning
- 3-second timeout per scan
- Synchronous API calls
- No caching mechanism

**Potential Optimizations:**
1. Implement async scanning
2. Add device caching with TTL
3. WebSocket for real-time updates
4. Background periodic scans
5. Multi-threaded subnet scanning

## Technology Choices & Rationale

| Technology | Choice | Rationale |
|------------|--------|-----------|
| Backend Framework | FastAPI | Modern, fast, async support, auto-docs |
| Frontend Framework | React | Component-based, popular, easy state management |
| Build Tool | Vite | Fast HMR, modern, optimized builds |
| Package Manager (Python) | uv | Extremely fast, modern, better than pip |
| Network Library | Scapy | Powerful, flexible, industry standard |
| HTTP Client | fetch | Native, no dependencies, simple |
| Styling | CSS | No framework overhead, full control |

## Future Architecture Enhancements

1. **Database Layer**
   - Add SQLite/PostgreSQL for device history
   - Track device uptime/downtime
   - Store device metadata

2. **Caching Layer**
   - Redis for device state caching
   - Reduce network scan frequency

3. **Real-time Updates**
   - WebSocket integration
   - Push updates to frontend
   - Live device status changes

4. **Authentication**
   - User login system
   - Role-based access control
   - Secure device management

5. **Advanced Features**
   - Port scanning
   - Wake-on-LAN support
   - Device control APIs
   - Network topology visualization

## File Structure

```
local-network/
├── backend/
│   ├── .venv/                 # Python virtual environment (uv)
│   ├── main.py               # FastAPI application & routing
│   ├── network_scanner.py    # Network discovery logic
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main React component
│   │   ├── App.css          # Component styles
│   │   ├── main.jsx         # React entry point
│   │   └── index.css        # Global styles
│   ├── public/              # Static assets
│   ├── package.json         # Node dependencies
│   └── vite.config.js       # Vite configuration
├── start.sh                 # Unified startup script
├── start-backend.sh         # Backend only
├── start-frontend.sh        # Frontend only
├── README.md               # User documentation
├── ARCHITECTURE.md         # This file
└── .gitignore             # Git ignore rules
```

## Development Workflow

1. **Setup:** Install dependencies with uv (backend) and npm (frontend)
2. **Development:** Run both servers concurrently
3. **Testing:** Manual testing via web interface
4. **Deployment:** Currently local only, designed for LAN use

## API Documentation

FastAPI automatically generates OpenAPI documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json
