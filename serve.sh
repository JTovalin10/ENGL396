#!/bin/bash
echo "Starting live-reload server..."
echo "Open your browser and go to: http://localhost:8000"
echo "Page will refresh automatically when files change."
echo "Press Ctrl+C to stop the server."
python3 "$(dirname "$0")/live_server.py"
