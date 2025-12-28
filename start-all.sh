#!/bin/bash
# Start Local Network Monitor (backend + frontend)

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  Starting Local Network Monitor"
echo "=========================================="
echo ""

# Create log directory and ensure proper permissions
mkdir -p ~/.local-network
touch ~/.local-network/backend.log
touch ~/.local-network/frontend.log
chmod 644 ~/.local-network/*.log 2>/dev/null || true

# Check if backend is already running
if pgrep -f "python.*main.py" > /dev/null; then
    echo "⚠️  Backend already running. Stop it first with: ./stop-all.sh"
    exit 1
fi

# Start backend
echo "🚀 Starting backend..."
cd "$PROJECT_DIR/backend"
nohup sudo .venv/bin/python main.py > ~/.local-network/backend.log 2>&1 &
BACKEND_PID=$!
sleep 2

# Check if backend started successfully
if pgrep -f "python.*main.py" > /dev/null; then
    echo "✅ Backend started (PID: $(pgrep -f 'python.*main.py'))"
    echo "   Logs: ~/.local-network/backend.log"
    echo "   API:  http://localhost:8000"
else
    echo "❌ Backend failed to start. Check logs: tail -f ~/.local-network/backend.log"
    exit 1
fi

echo ""

# Start frontend
echo "🚀 Starting frontend..."
cd "$PROJECT_DIR/frontend"
nohup npm run dev > ~/.local-network/frontend.log 2>&1 &
sleep 3

# Check if frontend started
if pgrep -f "vite" > /dev/null; then
    echo "✅ Frontend started (PID: $(pgrep -f 'vite'))"
    echo "   Logs: ~/.local-network/frontend.log"
    echo "   URL:  http://localhost:5173"
else
    echo "⚠️  Frontend may have failed to start. Check logs: tail -f ~/.local-network/frontend.log"
fi

echo ""
echo "=========================================="
echo "✅ Local Network Monitor is running!"
echo "=========================================="
echo ""
echo "  Open in browser: http://localhost:5173"
echo ""
echo "To stop: ./stop-all.sh"
echo "To view logs:"
echo "  Backend:  tail -f ~/.local-network/backend.log"
echo "  Frontend: tail -f ~/.local-network/frontend.log"
echo ""
