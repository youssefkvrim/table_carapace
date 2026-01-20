# KIOSK MODE SETUP - Step by Step Instructions

This guide will configure your Raspberry Pi to boot directly into the
Table Controle Carapace application in fullscreen mode.

---

## BEFORE YOU START

Make sure:
- The application works when you run it manually (`python3 app.py`)
- You have completed the initial setup (`./setup.sh`)
- You are connected to a keyboard and monitor

---

## STEP 1: Copy Files to Raspberry Pi

If not already done, copy all project files to the Pi:

```
/home/pi/Desktop/test_table/
├── app.py
├── autostart.sh
├── launch.sh
├── README.md
├── setup.sh
└── TODO_USER.md
```

---

## STEP 2: Make Scripts Executable

Open Terminal on the Raspberry Pi and run:

```bash
cd /home/pi/Desktop/test_table
chmod +x autostart.sh
chmod +x launch.sh
chmod +x setup.sh
```

---

## STEP 3: Enable Auto-Login to Console

We will configure the Pi to boot directly to a text console (no desktop),
and automatically log in as the "pi" user.

### 3.1 Open Raspberry Pi Configuration

```bash
sudo raspi-config
```

### 3.2 Navigate to Boot Options

Use arrow keys to navigate:

```
1. Select: "1 System Options"     → Press ENTER
2. Select: "S5 Boot / Auto Login" → Press ENTER
3. Select: "B2 Console Autologin" → Press ENTER
```

This means:
- B2 = Boot to text console (no graphical desktop)
- Autologin = Automatically log in as user "pi"

### 3.3 Exit raspi-config

```
Press RIGHT ARROW to select <Finish>
Press ENTER
```

If asked to reboot, select "No" for now (we have more steps).

---

## STEP 4: Configure Application to Start on Boot

We will add the autostart script to the pi user's shell profile.

### 4.1 Edit the .bashrc file

```bash
nano ~/.bashrc
```

### 4.2 Add autostart command at the END of the file

Scroll to the very bottom of the file (use arrow keys or Ctrl+End).
Add these lines at the end:

```bash
# ===========================================
# TABLE CONTROLE CARAPACE - AUTO START
# ===========================================
# Only run on tty1 (main console) to avoid running on SSH sessions
if [ "$(tty)" = "/dev/tty1" ]; then
    /home/pi/Desktop/test_table/autostart.sh
fi
```

### 4.3 Save and exit

```
Press Ctrl+O    (to save)
Press ENTER     (to confirm filename)
Press Ctrl+X    (to exit nano)
```

---

## STEP 5: Configure Console for Fullscreen Experience

### 5.1 Disable boot messages (cleaner startup)

```bash
sudo nano /boot/firmware/cmdline.txt
```

Find the line starting with `console=` and add these at the END of that line
(same line, just add a space and continue):

```
quiet splash loglevel=0 logo.nologo vt.global_cursor_default=0
```

The full line might look something like:
```
console=serial0,115200 console=tty1 root=PARTUUID=xxxxx rootfstype=ext4 ... quiet splash loglevel=0 logo.nologo vt.global_cursor_default=0
```

Save and exit (Ctrl+O, Enter, Ctrl+X).

### 5.2 Disable login messages

```bash
touch ~/.hushlogin
```

This hides the "Last login..." message.

---

## STEP 6: Optional - Increase Console Font Size

If the text is too small on your screen:

```bash
sudo dpkg-reconfigure console-setup
```

Navigate through the menus:
1. Encoding: UTF-8
2. Character set: Guess optimal
3. Font: Terminus (or TerminusBold)
4. Font size: 16x32 (or larger for bigger screens)

---

## STEP 7: Reboot and Test

```bash
sudo reboot
```

After reboot:
- The Pi should boot directly to a black screen
- Then automatically launch the Table Controle Carapace application
- The application runs fullscreen in the console

---

## HOW TO EXIT KIOSK MODE

### Temporarily exit (for maintenance)

While the application is running:
```
Press Ctrl+C     (stops the application)
Press Ctrl+C     (stops the auto-restart loop)
```

You will be at a command prompt. To restart the application:
```bash
/home/pi/Desktop/test_table/autostart.sh
```

### Permanently disable kiosk mode

1. Exit the application (Ctrl+C twice)
2. Edit .bashrc:
   ```bash
   nano ~/.bashrc
   ```
3. Delete or comment out the autostart section at the bottom
4. Save and exit

To re-enable desktop boot:
```bash
sudo raspi-config
```
Navigate to: System Options → Boot / Auto Login → B4 Desktop Autologin

---

## TROUBLESHOOTING

### Application doesn't start on boot

1. Check if autostart.sh is executable:
   ```bash
   ls -la /home/pi/Desktop/test_table/autostart.sh
   ```
   Should show `-rwxr-xr-x`. If not:
   ```bash
   chmod +x /home/pi/Desktop/test_table/autostart.sh
   ```

2. Check if .bashrc has the autostart lines:
   ```bash
   tail -10 ~/.bashrc
   ```

3. Test the script manually:
   ```bash
   /home/pi/Desktop/test_table/autostart.sh
   ```

### Screen is blank / nothing happens

1. Connect via SSH from another computer:
   ```bash
   ssh pi@raspberrypi.local
   ```
2. Check if app.py has errors:
   ```bash
   cd /home/pi/Desktop/test_table
   python3 app.py
   ```

### Want to access desktop temporarily

From command prompt after exiting the app:
```bash
startx
```

---

## SUMMARY OF CHANGES MADE

After following this guide, your Pi will:

1. Boot directly to console (no desktop)
2. Auto-login as user "pi"
3. Automatically run the Table Controle Carapace application
4. Display fullscreen (entire screen is the terminal)
5. Auto-restart the application if it exits

This creates a kiosk-like experience where users only see the application.

---

## SUPPORT

If you encounter issues:
- Email: youssef.karim@safrangroup.com

---

(C) 2025-2026 SAFRAN SA - Advanced Turbine Airfoils Platform
