# Table Controle Carapace

Safran SA ceramic shell photography system for crack detection after methylene blue testing.

## Run

```bash
cd ~/Desktop/table_carapace
python3 app.py
```

Or double-click `launch.sh`

## Setup (first time)

```bash
cd ~/Desktop/table_carapace
chmod +x setup.sh launch.sh autostart.sh
./setup.sh
sudo reboot
```

## Project Structure

```
table_carapace/
├── app.py                  # Entry point (backward-compatible)
├── table_carapace/         # Main application package
│   ├── __main__.py         # Package entry point
│   ├── application.py      # TUI menus and scan workflow
│   ├── config.py           # Configuration and settings persistence
│   ├── motor.py            # NEMA 23 stepper motor controller
│   ├── camera_pi.py        # Pi Camera V3 (CSI) controller
│   ├── camera_usb.py       # USB webcam (Logitech BRIO) controller
│   ├── camera_dual.py      # Dual camera manager
│   ├── camera_settings.py  # Live camera settings adjustment
│   ├── storage.py          # Scan file/folder management
│   ├── hardware.py         # Hardware imports with mock fallbacks
│   ├── logging_setup.py    # Logging configuration
│   └── ui.py               # Screen utilities and ASCII art
├── autostart.sh            # Kiosk mode auto-restart script
├── launch.sh               # Quick launch script
├── setup.sh                # First-time dependency installer
├── requirements.txt        # Python dependencies
└── TODO_USER.md            # Kiosk mode setup instructions
```

## Wiring

```
Pi GPIO 17 -> DM556 PUL+
Pi GND     -> DM556 PUL-
Pi GPIO 27 -> DM556 DIR+
Pi GND     -> DM556 DIR-
Pi GPIO 22 -> DM556 ENA+
Pi GND     -> DM556 ENA-
```

DM556 switches: SW1=ON SW2=ON SW3=OFF SW4=OFF

## Support

Contact: youssef.karim@safrangroup.com

(C) 2025-2026 SAFRAN SA - All Rights Reserved
