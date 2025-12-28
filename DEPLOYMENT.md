# Local Network Monitor - Deployment Guide

## Quick Start

### Start the application:
```bash
./start-all.sh
```

### Check status:
```bash
./status.sh
```

### Stop the application:
```bash
./stop-all.sh
```

### Access the application:
- **Frontend UI:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

---

## What Gets Started

1. **Backend** (FastAPI server on port 8000)
   - Network scanning every 30 seconds
   - Port scanning API
   - Pi-hole detection
   - SQLite database at `~/.local-network/db/devices.db`

2. **Frontend** (React + Vite on port 5173)
   - Device list with real-time updates
   - Port scanning interface
   - Device categorization
   - Sortable tables

---

## Logs

View logs in real-time:
```bash
# Backend logs
tail -f ~/.local-network/backend.log

# Frontend logs
tail -f ~/.local-network/frontend.log
```

---

## Troubleshooting

### Backend won't start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Check backend logs
tail -20 ~/.local-network/backend.log
```

### Frontend won't start
```bash
# Check if port 5173 is in use
lsof -i :5173

# Check frontend logs
tail -20 ~/.local-network/frontend.log

# Make sure dependencies are installed
cd frontend
npm install
```

### "Permission denied" errors
The backend needs sudo for network scanning:
```bash
# Run start script with sudo (it handles this automatically)
./start-all.sh
```

### Database issues
```bash
# Check database location
ls -lh ~/.local-network/db/

# Reset database (WARNING: deletes all history)
rm ~/.local-network/db/devices.db
```

---

## Running on System Startup (Optional)

If you want the monitor to start automatically when your Mac boots, see the LaunchAgents setup in the main README.

---

## Updating

After pulling new code:
```bash
# Stop services
./stop-all.sh

# Update backend dependencies (if needed)
cd backend
/Users/bob/.local/bin/uv pip install -r requirements.txt

# Update frontend dependencies (if needed)
cd ../frontend
npm install

# Restart services
cd ..
./start-all.sh
```

---

## Directory Structure

```
~/.local-network/
├── db/
│   └── devices.db          # SQLite database
├── backend.log             # Backend logs
└── frontend.log            # Frontend logs
```

---

## Ports Used

- **8000** - Backend API (FastAPI)
- **5173** - Frontend UI (Vite dev server)

Make sure these ports are available before starting.
