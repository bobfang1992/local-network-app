# Changelog

All notable changes to the Local Network Device Control Plane will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release with comprehensive network monitoring features
- Real-time network scanning using Scapy (ARP)
- WebSocket push architecture for real-time updates
- SQLite database for device persistence and history tracking
- Smart device categorization based on appearance frequency
  - NEW: First time seen (< 5 scans)
  - REGULAR: Seen in >70% of scans
  - OCCASIONAL: Seen in 30-70% of scans
  - RARE: Seen in <30% of scans
- Grace period system (3 missed scans before marking offline)
- Automatic hostname resolution via reverse DNS
- Manual notes for devices with inline editing
  - Click to edit mode
  - Press Enter to save
  - Press Escape to cancel
- Debug panel with database statistics
- CSV export functionality (copy to clipboard or download)
- Minimalist UI design inspired by usgraphics.com
- Color-coded device display:
  - Green tint for new devices
  - Blue tint for regular devices
  - Yellow tint for rare devices
  - Gray for offline devices
  - Blue-gray for regular devices currently offline
- Status panel with:
  - Connection status
  - Device count
  - Scan countdown timer with progress bar
  - Rolling scan log (last 5 events)
  - Color legend
- Tabbed interface (Devices / Debug)
- Development mode with auto-restart (watchdog)
- Passwordless sudo setup script
- Comprehensive documentation

### Backend
- FastAPI web framework with WebSocket support
- Continuous background scanner (30-second intervals)
- Pure Python network scanning (no subprocess)
- Scapy for ARP packet manipulation
- SQLite database with automatic schema migrations
- REST API endpoints:
  - `GET /` - API info
  - `GET /api/devices` - Current device list
  - `GET /api/database/stats` - Database statistics
  - `POST /api/devices/{ip}/notes` - Update device notes
- WebSocket endpoint:
  - `WS /ws` - Real-time device updates
- Device comparison algorithm with grace period
- Database functions:
  - Device CRUD operations
  - Scan history tracking
  - Device categorization
  - Notes management

### Frontend
- React 18 with Vite
- WebSocket client with auto-reconnect
- Real-time device table
- Inline note editing
- Countdown timer with visual progress bar
- Scan event log
- Debug panel with statistics
- CSV export (clipboard + download)
- Minimalist USGC-inspired design
- Color-coded table rows and badges

### Infrastructure
- Virtual environment setup with uv
- Python 3.13 compatibility
- Development watch script with watchdog
- Passwordless sudo configuration
- Git repository initialization
- Comprehensive README documentation
- Database auto-migration on schema changes

### Security
- Scoped sudo permissions (specific Python path only)
- Local network only (no external access)
- No authentication (trusted local network design)

## Version History

### [0.1.0] - 2025-12-28

Initial development version with all core features implemented.

**Features:**
- Real-time network device scanning
- WebSocket-based live updates
- Device history and categorization
- Manual device notes
- Debug panel and CSV export
- Minimalist UI with color coding
- Auto-restart development mode
- Passwordless sudo setup

**Technical Stack:**
- Backend: FastAPI, Scapy, SQLite, Watchdog
- Frontend: React 18, Vite
- Python 3.13, Node.js 18+

---

## Semantic Versioning Guide

Given a version number MAJOR.MINOR.PATCH:

- **MAJOR**: Incompatible API changes
- **MINOR**: New features (backwards-compatible)
- **PATCH**: Bug fixes (backwards-compatible)

## Change Categories

- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Vulnerability fixes
