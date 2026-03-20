#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting RepoAudit with Webscout...${NC}"

# Kill any existing processes on ports 5000 and 5173
echo -e "${YELLOW}Cleaning up old processes...${NC}"
fuser -k 5000/tcp 2>/dev/null
fuser -k 5173/tcp 2>/dev/null

# Start backend
echo -e "${GREEN}Starting Webscout backend on port 5000...${NC}"
cd ~/repo-auditor/backend
python3 webscout_backend.py > backend.log 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"

# Wait for backend to initialize
sleep 3

# Test backend
echo -e "${YELLOW}Testing backend connection...${NC}"
if curl -s http://localhost:5000/search > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Backend is responding${NC}"
else
  echo -e "${RED}❌ Backend not responding. Check backend.log${NC}"
  tail -20 backend.log
fi

# Start frontend
echo -e "${GREEN}Starting React frontend on port 5173...${NC}"
cd ~/repo-auditor
npm run dev -- --host > frontend.log 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}✅ Frontend started (PID: $FRONTEND_PID)${NC}"

echo -e "${BLUE}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Both services started successfully!${NC}"
echo -e "${YELLOW}📱 Frontend: ${NC}http://localhost:5173"
echo -e "${YELLOW}⚙️  Backend:  ${NC}http://localhost:5000"
echo -e "${YELLOW}📋 Logs:${NC}"
echo -e "   - Backend:  tail -f ~/repo-auditor/backend/backend.log"
echo -e "   - Frontend: tail -f ~/repo-auditor/frontend.log"
echo -e "${BLUE}══════════════════════════════════════════════════${NC}"
echo -e "${RED}Press Ctrl+C to stop both services${NC}"

# Handle shutdown
trap "echo -e '\n${YELLOW}Stopping services...${NC}'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo -e '${GREEN}✅ Services stopped${NC}'; exit" INT

# Keep script running
wait
