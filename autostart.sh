#!/bin/bash
# =============================================================================
# Table Controle Carapace - Kiosk Autostart Script
# =============================================================================
# This script launches the application in fullscreen terminal mode.
# It is called automatically on boot when kiosk mode is configured.
# =============================================================================

# Wait for system to fully boot
sleep 3

# Clear screen
clear

# Change to application directory
cd /home/pi/Desktop/test_table

# Run the application
# Loop ensures it restarts if it crashes or exits
while true; do
    python3 app.py
    
    # If app exits, show message and wait before restart
    echo ""
    echo "========================================"
    echo "  Application exited."
    echo "  Restarting in 5 seconds..."
    echo "  Press Ctrl+C to stop auto-restart."
    echo "========================================"
    sleep 5
    clear
done
