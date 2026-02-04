#!/bin/bash
# =============================================================================
# Table Controle Carapace - Kiosk Autostart Script
# =============================================================================
# This script launches the application in fullscreen terminal mode.
# It is called automatically on boot when kiosk mode is configured.
#
# Features:
#   - Crash counting with automatic pause after repeated failures
#   - Logging of crash events
#   - Graceful exit on Ctrl+C
# =============================================================================

APP_DIR="/home/pi/Desktop/test_table"
APP_LOG="${APP_DIR}/logs/autostart.log"
CRASH_COUNT_FILE="/tmp/table_controle_crash_count"
MAX_CRASHES=5
CRASH_RESET_SECONDS=300  # Reset crash counter after 5 minutes of stability

# Ensure log directory exists
mkdir -p "${APP_DIR}/logs"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $1" >> "$APP_LOG"
    echo "$1"
}

# Initialize or read crash counter
get_crash_count() {
    if [ -f "$CRASH_COUNT_FILE" ]; then
        cat "$CRASH_COUNT_FILE"
    else
        echo "0"
    fi
}

set_crash_count() {
    echo "$1" > "$CRASH_COUNT_FILE"
}

reset_crash_count() {
    set_crash_count 0
}

# Trap Ctrl+C for graceful exit
trap 'log_message "Autostart terminated by user (Ctrl+C)"; exit 0' INT

# Wait for system to fully boot
sleep 3

# Clear screen
clear

log_message "========================================="
log_message "Table Controle Carapace - Autostart"
log_message "========================================="

# Change to application directory
cd "$APP_DIR" || {
    log_message "ERROR: Cannot change to $APP_DIR"
    exit 1
}

# Main loop with crash counting
while true; do
    CRASH_COUNT=$(get_crash_count)
    
    # Check if we've hit the crash limit
    if [ "$CRASH_COUNT" -ge "$MAX_CRASHES" ]; then
        log_message "ERROR: Application crashed $CRASH_COUNT times consecutively"
        log_message "Pausing auto-restart for manual intervention"
        echo ""
        echo "========================================"
        echo "  APPLICATION CRASH LOOP DETECTED"
        echo "========================================"
        echo "  The application has crashed $CRASH_COUNT times."
        echo "  Auto-restart is paused to prevent damage."
        echo ""
        echo "  To investigate:"
        echo "    1. Check logs: cat ${APP_DIR}/logs/app.log"
        echo "    2. Test manually: python3 app.py"
        echo ""
        echo "  To resume auto-restart:"
        echo "    Press ENTER or reboot the system"
        echo "========================================"
        read -r
        reset_crash_count
        log_message "Crash counter reset by user, resuming auto-restart"
        clear
        continue
    fi
    
    START_TIME=$(date +%s)
    log_message "Starting application (attempt $((CRASH_COUNT + 1)))"
    
    # Run the application
    python3 app.py
    EXIT_CODE=$?
    
    END_TIME=$(date +%s)
    RUN_DURATION=$((END_TIME - START_TIME))
    
    log_message "Application exited with code $EXIT_CODE after ${RUN_DURATION}s"
    
    # If app ran for more than CRASH_RESET_SECONDS, reset crash counter
    # (indicates it was stable before exiting)
    if [ "$RUN_DURATION" -ge "$CRASH_RESET_SECONDS" ]; then
        log_message "Application was stable (ran ${RUN_DURATION}s), resetting crash counter"
        reset_crash_count
    else
        # Increment crash counter for rapid failures
        NEW_COUNT=$((CRASH_COUNT + 1))
        set_crash_count "$NEW_COUNT"
        log_message "Rapid exit detected, crash count: $NEW_COUNT/$MAX_CRASHES"
    fi
    
    # If user exited normally (exit code 0), don't count as crash
    if [ "$EXIT_CODE" -eq 0 ]; then
        log_message "Clean exit detected"
        reset_crash_count
    fi
    
    # Show restart message
    echo ""
    echo "========================================"
    echo "  Application exited (code: $EXIT_CODE)"
    echo "  Restarting in 5 seconds..."
    echo "  Press Ctrl+C to stop auto-restart."
    echo "========================================"
    sleep 5
    clear
done
