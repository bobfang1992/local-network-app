#!/bin/bash
# Stop Local Network Monitor (backend + frontend)

echo "=========================================="
echo "  Stopping Local Network Monitor"
echo "=========================================="
echo ""

# Stop backend
echo "🛑 Stopping backend..."
if pgrep -f "python.*main.py" > /dev/null; then
    sudo pkill -f "python.*main.py"
    sleep 1
    if pgrep -f "python.*main.py" > /dev/null; then
        echo "⚠️  Backend didn't stop gracefully, force killing..."
        sudo pkill -9 -f "python.*main.py"
    fi
    echo "✅ Backend stopped"
else
    echo "ℹ️  Backend not running"
fi

echo ""

# Stop frontend
echo "🛑 Stopping frontend..."
if pgrep -f "vite" > /dev/null; then
    pkill -f "vite"
    sleep 1
    if pgrep -f "vite" > /dev/null; then
        echo "⚠️  Frontend didn't stop gracefully, force killing..."
        pkill -9 -f "vite"
    fi
    echo "✅ Frontend stopped"
else
    echo "ℹ️  Frontend not running"
fi

echo ""
echo "=========================================="
echo "✅ Local Network Monitor stopped"
echo "=========================================="
echo ""
