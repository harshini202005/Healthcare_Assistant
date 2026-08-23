#!/bin/bash
# Healthcare Assistant - View Live Logs

echo "📋 Healthcare Assistant - Live Logs"
echo "===================================="
echo "Press Ctrl+C to exit"
echo ""

# Check if server is running
if ! lsof -ti:8000 > /dev/null 2>&1; then
    echo "⚠️  Server is not running!"
    echo ""
    echo "Start the server first:"
    echo "   ./start.sh"
    echo "   or"
    echo "   python main.py"
    exit 1
fi

# Follow the server log file
tail -f server.log
