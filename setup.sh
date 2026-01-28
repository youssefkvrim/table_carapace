#!/bin/bash
# =============================================================================
# Table Controle Carapace - Setup Script
# =============================================================================
# Run: chmod +x setup.sh && ./setup.sh
# =============================================================================

set -e

echo "=============================================="
echo "  TABLE CONTROLE CARAPACE - SETUP"
echo "=============================================="

echo ""
echo "[1/5] Updating packages..."
sudo apt update

echo ""
echo "[2/5] Installing dependencies..."
sudo apt install -y python3-pip python3-picamera2 python3-pil libcamera-apps

echo ""
echo "[3/5] Installing Python packages..."
# Note: gpiozero is pre-installed on Raspberry Pi OS and works with Pi 5
# RPi.GPIO does NOT work with Raspberry Pi 5
pip3 install --user Pillow --break-system-packages 2>/dev/null || pip3 install --user Pillow

echo ""
echo "[4/5] Creating directories..."
mkdir -p ~/Desktop/test_table/scans

echo ""
echo "[5/5] Making scripts executable..."
chmod +x ~/Desktop/test_table/launch.sh
chmod +x ~/Desktop/test_table/autostart.sh 2>/dev/null || true

echo ""
echo "=============================================="
echo "  SETUP COMPLETE"
echo "=============================================="
echo ""
echo "To run manually:"
echo "  python3 app.py"
echo ""
echo "To setup KIOSK MODE (fullscreen on boot):"
echo "  Read TODO_USER.md for step-by-step instructions"
echo ""
