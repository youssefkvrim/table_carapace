# Table Controle Carapace

Safran SA ceramic shell photography system.

## Run

```bash
cd ~/Desktop/test_table
python3 app.py
```

Or double-click `launch.sh`

## Setup (first time)

```bash
chmod +x setup.sh
./setup.sh
sudo reboot
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
