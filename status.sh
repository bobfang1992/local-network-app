#!/bin/bash
# Check status of Local Network Monitor services

echo "=========================================="
echo "  Local Network Monitor - Status"
echo "=========================================="
echo ""

# Check backend
echo "Backend:"
if pgrep -f "python.*main.py" > /dev/null; then
    BACKEND_PID=$(pgrep -f "python.*main.py")
    echo "  Status: ✅ Running (PID: $BACKEND_PID)"
    echo "  API:    http://localhost:8000"
    echo "  Logs:   tail -f ~/.local-network/backend.log"
else
    echo "  Status: ❌ Not running"
fi

echo ""

# Check frontend
echo "Frontend:"
if pgrep -f "vite" > /dev/null; then
    FRONTEND_PID=$(pgrep -f "vite")
    echo "  Status: ✅ Running (PID: $FRONTEND_PID)"
    echo "  URL:    http://localhost:5173"
    echo "  Logs:   tail -f ~/.local-network/frontend.log"
else
    echo "  Status: ❌ Not running"
fi

echo ""

# Check database
echo "Database:"
if [ -f ~/.local-network/db/devices.db ]; then
    DB_SIZE=$(du -h ~/.local-network/db/devices.db | cut -f1)
    echo "  Status: ✅ Exists"
    echo "  Size:   $DB_SIZE"
    echo "  Path:   ~/.local-network/db/devices.db"
else
    echo "  Status: ⚠️  Not yet created (will be created on first run)"
fi

echo ""
echo "=========================================="
echo ""
