#!/usr/bin/env python3
"""
Table Controle Carapace - Safran SA
Ceramic shell photography for crack detection after methylene blue test.
"""

import os
import sys
import time
import json
import threading
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================
class Config:
    # GPIO PINS (BCM numbering)
    GPIO_PULSE = 17
    GPIO_DIRECTION = 27
    GPIO_ENABLE = 22
    
    # MOTOR SETTINGS
    STEPS_PER_REVOLUTION = 800
    DEGREES_PER_STEP = 360.0 / 800
    ROTATION_INCREMENT = 15  # degrees per photo
    TOTAL_PHOTOS = 360 // 15  # 24 photos
    PULSE_DELAY_US = 500
    STEP_DELAY_MS = 5
    CALIBRATION_FACTOR = 1.0
    
    # CAMERA SETTINGS
    CAMERA_RESOLUTION = (4608, 2592)
    CAMERA_PREVIEW_SIZE = (800, 600)
    CAMERA_QUALITY = 95
    CAPTURE_DELAY = 0.5
    
    # STORAGE SETTINGS
    LOCAL_STORAGE_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "test_table", "scans")
    FILE_PREFIX = "grappe"
    FILE_EXTENSION = "jpg"
    
    # PIECE ID FORMAT - Change this pattern as needed
    # {:06d} = 6 digits zero-padded, P = suffix
    PIECE_ID_FORMAT = "{:06d}P"
    
    # NAS SETTINGS (placeholder for future implementation)
    NAS_ENABLED = False
    NAS_MOUNT_POINT = "/mnt/nas"
    NAS_TARGET_PATH = "/mnt/nas/inspection_images"
    # TODO: Configure these when NAS is available
    # NAS_IP = "192.168.1.100"
    # NAS_SHARE = "//192.168.1.100/share_name"
    # NAS_USERNAME = "your_username"
    # NAS_PASSWORD = "your_password"

CONFIG = Config()
CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")

# =============================================================================
# HARDWARE IMPORTS
# =============================================================================
# Using gpiozero for Raspberry Pi 5 compatibility (RPi.GPIO does NOT work on Pi 5)
try:
    from gpiozero import OutputDevice
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    # Mock for development on non-Pi systems
    class OutputDevice:
        def __init__(self, pin, initial_value=False):
            self.pin = pin
            self.value = 1 if initial_value else 0
        def on(self):
            self.value = 1
        def off(self):
            self.value = 0
        def close(self):
            pass

try:
    from picamera2 import Picamera2, Preview
    from libcamera import controls
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    Preview = None

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# =============================================================================
# ASCII ART
# =============================================================================
LOGO = r"""
               . ....---------:.....               
            ...------===============-..            
         ..=======-......   ....-======+..         
       .=====......                ...+++++..      
     .====...====...                   ..=+++..    
    :++..======..                         ..**+.   
 ..++..=======..                             .**.. 
..+..========-.                                .*..
.+..=========#.                                 ...
  .===========*...                                 
  .===============#....                            
  .================++++*#....                      
  ..==============++++++++**+*#....                
   ..+===========++++++++*******++=#+..            
     ..+========++++++++************++=-#.. .      
       ..-*====++++++++*****************+==#..     
            .**+++++++******************##*++=..   
               ...*#*******************#####***=.  
                   ....-###**********##########*.  
                           ...###***############.  
                                ...%%###########.  
.#..                               .*%#########..*.
 .#.                                .%########..#. 
 ..##..                            .*#######..##.  
    .##..                         .%#####*..##:    
     .+***....                ...:####...****..    
       ..***+=..               ......:****+.       
         ..+*++++++:...........:=++++++*.          
            ...+++++===========+++++..             
                 .....=======......                
"""

COMPANY_NAME = '''.dP"Y8    db    888888 88""Yb    db    88b 88
`Ybo."   dPYb   88__   88__dP   dPYb   88Yb88
o.`Y8b  dP__Yb  88""   88"Yb   dP__Yb  88 Y88
8bodP' dP""""Yb 88     88  Yb dP""""Yb 88  Y8

88""Yb 888888 Yb  dP
88__dP 88__    YbdP 
88"""  88""    dPYb 
88     88     dP  Yb'''

PROJECT_TITLE = r"""
 /$$$$$$$$        /$$       /$$                  /$$$$$$                        /$$                         /$$                 
|__  $$__/       | $$      | $$                 /$$__  $$                      | $$                        | $$                 
   | $$  /$$$$$$ | $$$$$$$ | $$  /$$$$$$       | $$  \__/  /$$$$$$  /$$$$$$$  /$$$$$$    /$$$$$$   /$$$$$$ | $$  /$$$$$$        
   | $$ |____  $$| $$__  $$| $$ /$$__  $$      | $$       /$$__  $$| $$__  $$|_  $$_/   /$$__  $$ /$$__  $$| $$ /$$__  $$       
   | $$  /$$$$$$$| $$  \ $$| $$| $$$$$$$$      | $$      | $$  \ $$| $$  \ $$  | $$    | $$  \__/| $$  \ $$| $$| $$$$$$$$       
   | $$ /$$__  $$| $$  | $$| $$| $$_____/      | $$    $$| $$  | $$| $$  | $$  | $$ /$$| $$      | $$  | $$| $$| $$_____/       
   | $$|  $$$$$$$| $$$$$$$/| $$|  $$$$$$$      |  $$$$$$/|  $$$$$$/| $$  | $$  |  $$$$/| $$      |  $$$$$$/| $$|  $$$$$$$       
   |__/ \_______/|_______/ |__/ \_______/       \______/  \______/ |__/  |__/   \___/  |__/       \______/ |__/ \_______/       

  /$$$$$$                                                                  
 /$$__  $$                                                                 
| $$  \__/  /$$$$$$   /$$$$$$  /$$$$$$   /$$$$$$   /$$$$$$   /$$$$$$$  /$$$$$$ 
| $$       |____  $$ /$$__  $$|____  $$ /$$__  $$ |____  $$ /$$_____/ /$$__  $$
| $$        /$$$$$$$| $$  \__/ /$$$$$$$| $$  \ $$  /$$$$$$$| $$      | $$$$$$$$
| $$    $$ /$$__  $$| $$      /$$__  $$| $$  | $$ /$$__  $$| $$      | $$_____/
|  $$$$$$/|  $$$$$$$| $$     |  $$$$$$$| $$$$$$$/|  $$$$$$$|  $$$$$$$|  $$$$$$$
 \______/  \_______/|__/      \_______/| $$____/  \_______/ \_______/ \_______/
                                       | $$                                    
                                       | $$                                    
                                       |__/                                    
"""

LICENSE_TEXT = """
================================================================================
                        PROPRIETARY SOFTWARE LICENSE
================================================================================

  This software is the exclusive property of SAFRAN SA and was developed for
  the Advanced Turbine Airfoils Platform division.

  PURPOSE: Ceramic shell photography system (Table de Prise de Photo des
  Carapaces Ceramiques) for crack detection following methylene blue testing.

  RESTRICTIONS:
    - Unauthorized copying, modification, or distribution is strictly prohibited
    - This software is licensed for use only on authorized SAFRAN equipment
    - Reverse engineering or decompilation is not permitted
    - All intellectual property rights remain with SAFRAN SA

  LEGAL NOTICE:
    Any unauthorized reproduction, distribution, modification, or use of this
    software constitutes a violation of intellectual property law and may
    result in civil and criminal penalties under applicable French and
    international regulations.

  SUPPORT & ISSUES:
    Contact: youssef.karim@safrangroup.com

  (C) 2025-2026 SAFRAN SA - All Rights Reserved
================================================================================
"""

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def progress_bar(current, total, prefix="Progress", length=50):
    percent = current / total if total > 0 else 0
    filled = int(length * percent)
    bar = "█" * filled + "░" * (length - filled)
    print(f"\r{prefix} |{bar}| {current}/{total} ({percent*100:.1f}%)", end="", flush=True)
    if current == total:
        print()

def load_calibration():
    try:
        if os.path.exists(CALIBRATION_FILE):
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                CONFIG.CALIBRATION_FACTOR = data.get('calibration_factor', 1.0)
                return CONFIG.CALIBRATION_FACTOR
    except Exception:
        pass
    return 1.0

def save_calibration(factor):
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump({'calibration_factor': factor}, f, indent=2)
        CONFIG.CALIBRATION_FACTOR = factor
        return True
    except Exception:
        return False

def print_side_by_side(left, right, left_width=55):
    """Print two multi-line strings side by side."""
    left_lines = left.split('\n')
    right_lines = right.strip().split('\n')
    
    # Remove empty first/last lines from left (preserves internal spacing)
    if left_lines and left_lines[0] == '':
        left_lines = left_lines[1:]
    if left_lines and left_lines[-1] == '':
        left_lines = left_lines[:-1]
    
    max_lines = max(len(left_lines), len(right_lines))
    
    for i in range(max_lines):
        left_line = left_lines[i] if i < len(left_lines) else ""
        right_line = right_lines[i] if i < len(right_lines) else ""
        print(f"{left_line:<{left_width}} {right_line}")

# =============================================================================
# MOTOR CONTROLLER
# =============================================================================
class MotorController:
    """Controls NEMA 23 stepper motor via DM556 driver using gpiozero (Pi 5 compatible)."""
    
    def __init__(self):
        self.current_angle = 0.0
        self.is_enabled = False
        
        # Initialize GPIO pins using gpiozero OutputDevice
        # initial_value=False means pin starts LOW, True means HIGH
        self.pulse_pin = OutputDevice(CONFIG.GPIO_PULSE, initial_value=False)
        self.direction_pin = OutputDevice(CONFIG.GPIO_DIRECTION, initial_value=False)
        self.enable_pin = OutputDevice(CONFIG.GPIO_ENABLE, initial_value=True)  # HIGH = disabled
    
    def enable(self):
        """Enable motor driver (ENA is active LOW on DM556)."""
        self.enable_pin.off()  # LOW = enabled
        self.is_enabled = True
        time.sleep(0.01)
    
    def disable(self):
        """Disable motor driver."""
        self.enable_pin.on()  # HIGH = disabled
        self.is_enabled = False
    
    def step(self, num_steps, delay_us=None):
        """Execute step pulses."""
        if delay_us is None:
            delay_us = CONFIG.PULSE_DELAY_US
        delay_s = delay_us / 1_000_000
        for _ in range(num_steps):
            self.pulse_pin.on()
            time.sleep(delay_s)
            self.pulse_pin.off()
            time.sleep(delay_s)
            time.sleep(CONFIG.STEP_DELAY_MS / 1000)
    
    def rotate_degrees(self, degrees, clockwise=True):
        """Rotate motor by specified degrees."""
        if not self.is_enabled:
            self.enable()
        calibrated = degrees * CONFIG.CALIBRATION_FACTOR
        steps = round(calibrated / CONFIG.DEGREES_PER_STEP)
        
        # Set direction
        if clockwise:
            self.direction_pin.on()
        else:
            self.direction_pin.off()
        time.sleep(0.001)
        
        self.step(steps)
        
        if clockwise:
            self.current_angle = (self.current_angle + degrees) % 360
        else:
            self.current_angle = (self.current_angle - degrees) % 360
        return degrees
    
    def rotate_increment(self):
        """Rotate by configured increment."""
        self.rotate_degrees(CONFIG.ROTATION_INCREMENT, clockwise=True)
        return self.current_angle
    
    def reset_position(self):
        """Reset angle tracking to zero."""
        self.current_angle = 0.0
    
    def cleanup(self):
        """Release GPIO resources."""
        self.disable()
        self.pulse_pin.close()
        self.direction_pin.close()
        self.enable_pin.close()

# =============================================================================
# CAMERA CONTROLLER
# =============================================================================
class CameraController:
    """Camera controller with live preview support via OpenCV or native Picamera2."""
    
    PREVIEW_WINDOW = "Camera Preview - Press Q to close"
    
    def __init__(self):
        self.camera = None
        self.is_initialized = False
        self.preview_active = False
        self.preview_thread = None
        self.stop_preview_flag = False
        
        if CAMERA_AVAILABLE:
            self._initialize()
    
    def _initialize(self):
        try:
            self.camera = Picamera2()
            config = self.camera.create_still_configuration(
                main={"size": CONFIG.CAMERA_RESOLUTION, "format": "RGB888"},
                lores={"size": CONFIG.CAMERA_PREVIEW_SIZE, "format": "RGB888"},
                buffer_count=2
            )
            self.camera.configure(config)
            self.camera.set_controls({
                "AfMode": controls.AfModeEnum.Continuous,
                "AfSpeed": controls.AfSpeedEnum.Normal,
            })
            self.camera.start()
            time.sleep(2)
            self.is_initialized = True
        except Exception as e:
            print(f"  [CAMERA] Init failed: {e}")
            self.camera = None
    
    def start_preview(self):
        """Start live video preview window using OpenCV or native preview."""
        if not CAMERA_AVAILABLE or not self.is_initialized:
            print("  [CAMERA] Not available - running in mock mode")
            return False
        
        # Prefer OpenCV for reliable cross-platform preview
        if CV2_AVAILABLE:
            return self._start_opencv_preview()
        
        # Fallback to native Picamera2 preview
        return self._start_native_preview()
    
    def _start_opencv_preview(self):
        """Start preview using OpenCV window (non-blocking via thread)."""
        self.stop_preview_flag = False
        self.preview_thread = threading.Thread(target=self._opencv_preview_loop, daemon=True)
        self.preview_thread.start()
        self.preview_active = True
        return True
    
    def _opencv_preview_loop(self):
        """OpenCV preview loop running in separate thread."""
        cv2.namedWindow(self.PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.PREVIEW_WINDOW, 800, 600)
        
        while not self.stop_preview_flag:
            try:
                # Capture low-res frame for preview
                frame = self.camera.capture_array("lores")
                # Convert RGB to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                cv2.imshow(self.PREVIEW_WINDOW, frame_bgr)
                
                key = cv2.waitKey(30) & 0xFF
                if key == ord('q'):
                    break
            except Exception:
                break
        
        cv2.destroyAllWindows()
    
    def _start_native_preview(self):
        """Start preview using Picamera2 native preview."""
        try:
            try:
                self.camera.start_preview(Preview.QT, x=100, y=100, width=800, height=600)
            except Exception:
                try:
                    self.camera.start_preview(Preview.QTGL, x=100, y=100, width=800, height=600)
                except Exception:
                    try:
                        self.camera.start_preview(Preview.DRM, x=100, y=100, width=800, height=600)
                    except Exception:
                        self.camera.start_preview(Preview.NULL)
                        print("  [CAMERA] Preview window not available on this system")
                        return False
            
            self.preview_active = True
            return True
        except Exception as e:
            print(f"  [CAMERA] Preview failed: {e}")
            return False
    
    def stop_preview(self):
        """Stop live video preview."""
        self.stop_preview_flag = True
        
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=1.0)
        
        if CV2_AVAILABLE:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        
        if self.preview_active and self.camera:
            try:
                self.camera.stop_preview()
            except Exception:
                pass
        
        self.preview_active = False
    
    def capture(self, filepath):
        """Capture and save an image."""
        if not CAMERA_AVAILABLE:
            return self._mock_capture(filepath)
        if not self.is_initialized:
            return False
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            self.camera.set_controls({"AfTrigger": controls.AfTriggerEnum.Start})
            time.sleep(0.3)
            self.camera.capture_file(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            print(f"  [CAMERA] Capture error: {e}")
            return False
    
    def _mock_capture(self, filepath):
        """Create mock image for testing without camera."""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            if PIL_AVAILABLE:
                img = Image.new('RGB', (640, 480), color='white')
                img.save(filepath, 'JPEG', quality=CONFIG.CAMERA_QUALITY)
            else:
                with open(filepath, 'w') as f:
                    f.write("MOCK")
            return True
        except Exception:
            return False
    
    def get_status(self):
        """Get current camera status info."""
        if not CAMERA_AVAILABLE or not self.is_initialized:
            return "MOCK MODE"
        try:
            metadata = self.camera.capture_metadata()
            focus = metadata.get("FocusFoM", "N/A")
            exposure = metadata.get("ExposureTime", "N/A")
            return f"Focus: {focus} | Exp: {exposure}us"
        except Exception:
            return "Active"
    
    def cleanup(self):
        """Clean up camera resources."""
        self.stop_preview()
        if self.camera:
            try:
                self.camera.stop()
                self.camera.close()
            except Exception:
                pass
        self.is_initialized = False

# =============================================================================
# STORAGE MANAGER
# =============================================================================
class StorageManager:
    def __init__(self):
        self.local_path = CONFIG.LOCAL_STORAGE_PATH
        self.current_piece_id = None
        self.current_folder = None
        os.makedirs(self.local_path, exist_ok=True)
    
    def set_piece_id(self, piece_number):
        self.current_piece_id = CONFIG.PIECE_ID_FORMAT.format(int(piece_number))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_folder = os.path.join(self.local_path, f"{self.current_piece_id}_{timestamp}")
        os.makedirs(self.current_folder, exist_ok=True)
        return self.current_piece_id
    
    def get_filepath(self, angle):
        if not self.current_piece_id:
            raise ValueError("Piece ID not set")
        filename = f"{CONFIG.FILE_PREFIX}_{self.current_piece_id}_{int(angle):03d}deg.{CONFIG.FILE_EXTENSION}"
        return os.path.join(self.current_folder, filename)
    
    def get_image_count(self):
        if not self.current_folder or not os.path.exists(self.current_folder):
            return 0
        return len([f for f in os.listdir(self.current_folder) if f.endswith(f".{CONFIG.FILE_EXTENSION}")])
    
    def transfer_to_nas(self):
        # TODO: Implement NAS transfer when configured
        if CONFIG.NAS_ENABLED:
            print("  [STORAGE] NAS transfer not yet implemented")
        return False

# =============================================================================
# MAIN APPLICATION
# =============================================================================
class Application:
    def __init__(self):
        self.motor = None
        self.camera = None
        self.storage = None
        load_calibration()
    
    def show_header(self):
        """Display the persistent header with logo, company, license, and title."""
        clear_screen()
        
        # Logo and company name side by side
        print_side_by_side(LOGO, COMPANY_NAME, left_width=55)
        
        # License text
        print(LICENSE_TEXT)
        
        # Project title
        print(PROJECT_TITLE)
    
    def show_main_menu(self):
        """Display main menu options."""
        self.show_header()
        
        print("\n" + "=" * 100)
        print("                                      MAIN MENU")
        print("=" * 100)
        print(f"\n  Current Settings: Increment={CONFIG.ROTATION_INCREMENT}deg | Photos={CONFIG.TOTAL_PHOTOS} | Calibration={CONFIG.CALIBRATION_FACTOR:.4f}")
        print(f"  Storage: {CONFIG.LOCAL_STORAGE_PATH}")
        print("\n" + "-" * 100)
        print("\n    [1] LAUNCH CAPTURE        Start 360 degree scan with live preview")
        print("    [2] TEST CAMERA           View continuous video feed (no saving)")
        print("    [3] TEST MOTOR            Motor control and calibration")
        print("    [4] INFORMATION           Wiring diagram and documentation")
        print("    [0] EXIT")
        print("\n" + "=" * 100)
    
    def run(self):
        """Main application loop."""
        while True:
            self.show_main_menu()
            choice = input("\n  Enter option: ").strip()
            
            if choice == "1":
                self.launch_capture()
            elif choice == "2":
                self.test_camera()
            elif choice == "3":
                self.test_motor_menu()
            elif choice == "4":
                self.show_information()
            elif choice == "0":
                print("\n  Exiting. Goodbye.")
                break
    
    def launch_capture(self):
        """Run full 360 degree capture with live preview."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                   360 DEGREE CAPTURE")
        print("=" * 100)
        
        try:
            piece_input = input("\n  Enter piece number (or 'q' to cancel): ").strip()
            if piece_input.lower() == 'q':
                return
            piece_number = int(piece_input)
        except ValueError:
            print("  Invalid number.")
            time.sleep(1)
            return
        
        print("\n  Initializing hardware...")
        progress_bar(0, 3, "  Init")
        
        self.motor = MotorController()
        progress_bar(1, 3, "  Init")
        
        self.camera = CameraController()
        progress_bar(2, 3, "  Init")
        
        self.storage = StorageManager()
        piece_id = self.storage.set_piece_id(piece_number)
        progress_bar(3, 3, "  Init")
        
        print(f"\n  Piece ID: {piece_id}")
        print(f"  Output: {self.storage.current_folder}")
        
        # Start live preview
        print("\n  Starting live preview...")
        preview_ok = self.camera.start_preview()
        if preview_ok:
            print("  [PREVIEW] Live video window opened")
        else:
            print("  [PREVIEW] Running without preview window")
        
        print(f"\n  Starting scan... Press Ctrl+C to abort.\n")
        
        self.motor.enable()
        self.motor.reset_position()
        
        captured = 0
        try:
            for i in range(CONFIG.TOTAL_PHOTOS):
                current_angle = i * CONFIG.ROTATION_INCREMENT
                
                # Status update
                status = self.camera.get_status()
                print(f"  [{i+1:2d}/{CONFIG.TOTAL_PHOTOS}] Angle: {current_angle:03d}deg | {status} | ", end="")
                
                time.sleep(CONFIG.CAPTURE_DELAY)
                
                # Capture and save
                filepath = self.storage.get_filepath(current_angle)
                success = self.camera.capture(filepath)
                
                if success:
                    captured += 1
                    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    print(f"SAVED ({size/1024:.0f}KB)")
                else:
                    print("FAILED")
                
                progress_bar(i + 1, CONFIG.TOTAL_PHOTOS, "  Progress")
                
                # Rotate to next position
                if i < CONFIG.TOTAL_PHOTOS - 1:
                    self.motor.rotate_increment()
        
        except KeyboardInterrupt:
            print("\n\n  Scan aborted by user.")
        
        finally:
            self.camera.stop_preview()
            self.motor.disable()
            self.motor.cleanup()
            self.camera.cleanup()
        
        print("\n" + "=" * 100)
        print(f"  SCAN COMPLETE: {captured}/{CONFIG.TOTAL_PHOTOS} images")
        print(f"  Location: {self.storage.current_folder}")
        print("=" * 100)
        
        if CONFIG.NAS_ENABLED:
            print("  Transferring to NAS...")
            self.storage.transfer_to_nas()
        
        input("\n  Press ENTER to continue...")
    
    def test_camera(self):
        """Test camera with live video preview only (no saving)."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                CAMERA TEST - LIVE PREVIEW")
        print("=" * 100)
        
        self.camera = CameraController()
        
        if not self.camera.is_initialized and CAMERA_AVAILABLE:
            print("\n  Camera not initialized. Check connection.")
            input("\n  Press ENTER to continue...")
            return
        
        # Start preview window
        preview_ok = self.camera.start_preview()
        
        if preview_ok:
            if CV2_AVAILABLE:
                print("\n  [PREVIEW] Live video window opened (OpenCV)")
                print("  [PREVIEW] Press 'Q' in the preview window OR Ctrl+C here to stop")
            else:
                print("\n  [PREVIEW] Live video window opened (native)")
                print("  [PREVIEW] Press Ctrl+C to stop")
        else:
            print("\n  [PREVIEW] Could not open preview window.")
            if not CAMERA_AVAILABLE:
                print("  [PREVIEW] Camera hardware not detected (mock mode).")
        
        print("\n  Streaming live video...\n")
        
        try:
            frame = 0
            while True:
                # Check if OpenCV preview thread stopped (user pressed Q)
                if CV2_AVAILABLE and self.camera.preview_thread:
                    if not self.camera.preview_thread.is_alive():
                        print("\n\n  Preview window closed.")
                        break
                
                frame += 1
                status = self.camera.get_status()
                print(f"\r  [LIVE] Frame {frame:05d} | {status}          ", end="", flush=True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        
        print("\n\n  Stopping preview...")
        self.camera.cleanup()
        
        input("\n  Press ENTER to continue...")
    
    def test_motor_menu(self):
        """Motor test and calibration menu."""
        while True:
            self.show_header()
            print("\n" + "=" * 100)
            print("                                MOTOR TEST & CALIBRATION")
            print("=" * 100)
            print(f"\n  Current: Increment={CONFIG.ROTATION_INCREMENT}deg | Calibration={CONFIG.CALIBRATION_FACTOR:.6f}")
            print(f"  Speed: Pulse={CONFIG.PULSE_DELAY_US}us | Step={CONFIG.STEP_DELAY_MS}ms")
            print("\n" + "-" * 100)
            print("\n    [1] ROTATE BY DEGREES     Enter custom rotation angle")
            print(f"    [2] MODIFY INCREMENT      Change rotation increment (current: {CONFIG.ROTATION_INCREMENT})")
            print("    [3] MODIFY SPEED          Change motor speed settings")
            print("    [4] CALIBRATION           Adjust calibration factor")
            print("    [0] BACK TO MAIN MENU")
            print("\n" + "=" * 100)
            
            choice = input("\n  Enter option: ").strip()
            
            if choice == "1":
                self.motor_rotate_test()
            elif choice == "2":
                self.modify_increment()
            elif choice == "3":
                self.modify_speed()
            elif choice == "4":
                self.motor_calibration()
            elif choice == "0":
                break
    
    def motor_rotate_test(self):
        """Interactive motor rotation test."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                  MOTOR ROTATION TEST")
        print("=" * 100)
        print("  Enter degrees to rotate. Type 'q' to quit, 'r' to reset position.\n")
        
        self.motor = MotorController()
        self.motor.enable()
        
        try:
            while True:
                print(f"\n  Current angle: {self.motor.current_angle:.2f} degrees")
                degrees_input = input("  Degrees (or 'q'/'r'): ").strip()
                
                if degrees_input.lower() == 'q':
                    break
                if degrees_input.lower() == 'r':
                    self.motor.reset_position()
                    print("  Position reset to 0 degrees")
                    continue
                
                try:
                    degrees = float(degrees_input)
                    direction = input("  Direction CW/CCW [CW]: ").strip().upper()
                    clockwise = direction != 'CCW'
                    
                    print(f"  Rotating {degrees} degrees {'CW' if clockwise else 'CCW'}...")
                    self.motor.rotate_degrees(degrees, clockwise)
                    print(f"  Done. New angle: {self.motor.current_angle:.2f} degrees")
                except ValueError:
                    print("  Invalid input.")
        
        except KeyboardInterrupt:
            print("\n  Interrupted.")
        
        finally:
            self.motor.disable()
            self.motor.cleanup()
    
    def modify_increment(self):
        """Modify rotation increment."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                MODIFY ROTATION INCREMENT")
        print("=" * 100)
        print(f"\n  Current increment: {CONFIG.ROTATION_INCREMENT} degrees")
        print(f"  Total photos per scan: {CONFIG.TOTAL_PHOTOS}")
        
        try:
            new_val = input("\n  Enter new increment (degrees): ").strip()
            if new_val:
                new_increment = int(new_val)
                if 360 % new_increment == 0 and new_increment > 0:
                    CONFIG.ROTATION_INCREMENT = new_increment
                    CONFIG.TOTAL_PHOTOS = 360 // new_increment
                    print(f"\n  Increment set to {new_increment} degrees")
                    print(f"  Total photos per scan: {CONFIG.TOTAL_PHOTOS}")
                else:
                    print("  Increment must divide 360 evenly.")
        except ValueError:
            print("  Invalid input.")
        
        input("\n  Press ENTER to continue...")
    
    def modify_speed(self):
        """Modify motor speed settings."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                  MODIFY MOTOR SPEED")
        print("=" * 100)
        print(f"\n  Current pulse delay: {CONFIG.PULSE_DELAY_US} microseconds")
        print(f"  Current step delay: {CONFIG.STEP_DELAY_MS} milliseconds")
        print("\n  Lower pulse delay = faster rotation (min recommended: 100us)")
        
        try:
            pulse_input = input(f"\n  Pulse delay [100-5000] ({CONFIG.PULSE_DELAY_US}): ").strip()
            if pulse_input:
                pulse = int(pulse_input)
                CONFIG.PULSE_DELAY_US = max(100, min(5000, pulse))
                print(f"  Pulse delay set to {CONFIG.PULSE_DELAY_US} microseconds")
            
            step_input = input(f"  Step delay [1-50] ({CONFIG.STEP_DELAY_MS}): ").strip()
            if step_input:
                step = int(step_input)
                CONFIG.STEP_DELAY_MS = max(1, min(50, step))
                print(f"  Step delay set to {CONFIG.STEP_DELAY_MS} milliseconds")
        except ValueError:
            print("  Invalid input.")
        
        input("\n  Press ENTER to continue...")
    
    def motor_calibration(self):
        """Motor calibration menu."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                  MOTOR CALIBRATION")
        print("=" * 100)
        print(f"\n  Current calibration factor: {CONFIG.CALIBRATION_FACTOR:.6f}")
        print("\n  Factor > 1.0 = motor rotates less than expected")
        print("  Factor < 1.0 = motor rotates more than expected")
        print("\n" + "-" * 100)
        print("\n    [1] Test 360 rotation (measure actual)")
        print("    [2] Enter calibration factor manually")
        print("    [3] Reset to 1.0")
        print("    [0] Back")
        print("\n" + "=" * 100)
        
        choice = input("\n  Enter option: ").strip()
        
        if choice == "1":
            self._calibration_test()
        elif choice == "2":
            self._calibration_manual()
        elif choice == "3":
            save_calibration(1.0)
            print("\n  Calibration reset to 1.0")
            input("  Press ENTER to continue...")
    
    def _calibration_test(self):
        """Run 360 degree calibration test."""
        self.motor = MotorController()
        self.motor.enable()
        self.motor.reset_position()
        
        print("\n  Rotating 360 degrees...")
        progress_bar(0, 360, "  Rotation")
        
        # Rotate in increments for progress display
        for i in range(24):
            self.motor.rotate_degrees(15, clockwise=True)
            progress_bar((i + 1) * 15, 360, "  Rotation")
        
        self.motor.disable()
        self.motor.cleanup()
        
        print("\n  Measure the actual rotation of your reference mark.")
        try:
            actual = float(input("  Enter actual degrees rotated: ").strip())
            error = actual - 360.0
            print(f"\n  Error: {error:+.2f} degrees")
            
            if abs(error) > 0.1 and actual > 0:
                suggested = 360.0 / actual
                print(f"  Suggested calibration factor: {suggested:.6f}")
                save_calibration(suggested)
                print(f"  Calibration saved: {suggested:.6f}")
            else:
                print("  Rotation is accurate. No calibration needed.")
        except ValueError:
            print("  Invalid input.")
        
        input("\n  Press ENTER to continue...")
    
    def _calibration_manual(self):
        """Manually enter calibration factor."""
        try:
            new_factor = float(input("\n  Enter new calibration factor: ").strip())
            if new_factor > 0:
                save_calibration(new_factor)
                print(f"  Calibration saved: {new_factor:.6f}")
            else:
                print("  Factor must be positive.")
        except ValueError:
            print("  Invalid input.")
        
        input("\n  Press ENTER to continue...")
    
    def show_information(self):
        """Display system information and wiring diagram."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                 SYSTEM INFORMATION")
        print("=" * 100)
        print("""
  HARDWARE COMPONENTS
  -------------------
    - Raspberry Pi 5
    - Pi Camera V3 (IMX708) - 12MP
    - NEMA 23 Stepper Motor (23HS32-4004S)
    - DM556 Stepper Driver
    - 24-48V DC Power Supply

  WIRING DIAGRAM
  --------------
    Raspberry Pi 5              DM556 Driver
    +--------------+            +------------+
    | GPIO 17 (11) |----------->| PUL+       |
    | GND (6)      |----------->| PUL-       |
    | GPIO 27 (13) |----------->| DIR+       |
    | GND (14)     |----------->| DIR-       |
    | GPIO 22 (15) |----------->| ENA+       |
    | GND (20)     |----------->| ENA-       |
    +--------------+            +------------+

  DM556 DIP SWITCHES
  ------------------
    SW1: ON   (800 steps/revolution)
    SW2: ON
    SW3: OFF
    SW4: OFF
    SW5-SW8: Set according to motor current rating

  OPERATION
  ---------
    1. Place ceramic shell on rotating table
    2. Launch capture (option 1)
    3. Enter piece number
    4. System rotates 15 degrees, captures image, repeats 24 times
    5. Images saved to: ~/Desktop/test_table/scans/

  FILE NAMING
  -----------
    Format: grappe_XXXXXXP_XXXdeg.jpg
    Example: grappe_000001P_015deg.jpg

  SUPPORT
  -------
    Contact: youssef.karim@safrangroup.com
""")
        print("=" * 100)
        input("\n  Press ENTER to continue...")

# =============================================================================
# ENTRY POINT
# =============================================================================
def main():
    try:
        app = Application()
        app.run()
    except KeyboardInterrupt:
        print("\n\n  Program terminated.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
