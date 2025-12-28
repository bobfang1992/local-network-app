#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Local Network Device Control Plane${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down servers...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}Servers stopped. Goodbye!${NC}"
    exit 0
}

# Trap Ctrl+C and call cleanup
trap cleanup INT TERM

# Start backend
echo -e "${GREEN}[1/2] Starting FastAPI backend...${NC}"
cd backend
source .venv/bin/activate
python main.py &
BACKEND_PID=$!
cd ..

# Wait a bit for backend to start
sleep 2

# Check if backend started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${YELLOW}Error: Backend failed to start${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Backend running on http://localhost:8000${NC}"
echo ""

# Start frontend
echo -e "${GREEN}[2/2] Starting React frontend...${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait a bit for frontend to start
sleep 3

# Check if frontend started successfully
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${YELLOW}Error: Frontend failed to start${NC}"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Frontend running on http://localhost:5173${NC}"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ All servers are running!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Open your browser and visit: ${BLUE}http://localhost:5173${NC}"
echo -e "API documentation available at: ${BLUE}http://localhost:8000/docs${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all servers${NC}"
echo ""

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
