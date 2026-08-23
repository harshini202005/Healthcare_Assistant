#!/bin/bash
# Healthcare Assistant - Quick Start Script
# One command to start both frontend and backend

echo "🏥 Healthcare Assistant - Quick Start"
echo "======================================"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies if needed
if [ ! -f ".venv/installed" ]; then
    echo "📥 Installing dependencies..."
    pip install -r requirements.txt
    touch .venv/installed
fi

# Start the server (frontend + backend + auto-open browser)
echo ""
echo "🚀 Starting Healthcare Assistant..."
echo "🌐 Frontend + Backend: http://localhost:8000"
echo "📱 Browser will open automatically"
echo ""
echo "⏹️  Press Ctrl+C to stop"
echo "======================================"
echo ""

python main.py