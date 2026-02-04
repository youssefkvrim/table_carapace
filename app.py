#!/usr/bin/env python3
"""
Table Controle Carapace - Safran SA
Ceramic shell photography for crack detection after methylene blue test.
"""

import os
import sys
import time
import json
import gc
import threading
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# =============================================================================
# LOGGING SETUP
# =============================================================================
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Configure rotating file handler (5MB max, keep 3 backups)
_file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# Configure console handler (errors only to avoid cluttering UI)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.ERROR)
_console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

# Root logger
logging.basicConfig(level=logging.DEBUG, handlers=[_file_handler, _console_handler])

# Module loggers
log_main = logging.getLogger("main")
log_motor = logging.getLogger("motor")
log_camera = logging.getLogger("camera")
log_storage = logging.getLogger("storage")

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
    ROTATION_INCREMENT = 15  # degrees per photo (must be 5-90 and divide 360 evenly)
    TOTAL_PHOTOS = 360 // 15  # 24 photos
    # Note: Python time.sleep() has ~1ms granularity on Linux; values below 1ms are approximate
    PULSE_DELAY_MS = 0.5      # delay for each pulse edge (minimum reliable: ~0.5ms)
    STEP_DELAY_MS = 5         # delay between steps
    CALIBRATION_FACTOR = 1.0
    
    # VIDEO SETTINGS
    VIDEO_CODEC = "mp4v"      # Options: "mp4v" (compatible), "avc1" (H.264, smaller), "XVID", "MJPG"
    VIDEO_FPS = 15            # Frames per second for scan video
    
    # PI CAMERA SETTINGS (CSI - Camera Module V3)
    CAMERA_RESOLUTION = (4608, 2592)
    CAMERA_PREVIEW_SIZE = (800, 600)
    CAMERA_QUALITY = 95
    CAPTURE_DELAY = 0.5
    # Set to True if preview colors are wrong (swap R and B channels)
    PREVIEW_SWAP_RB = False
    
    # USB CAMERA SETTINGS (Logitech BRIO or similar)
    USB_CAMERA_ENABLED = True
    USB_CAMERA_INDEX = 0      # Will auto-detect if this fails
    USB_CAMERA_RESOLUTION = (1920, 1080)
    USB_CAMERA_PREVIEW_SIZE = (640, 480)
    
    # DUAL CAMERA MODE
    DUAL_CAMERA_ENABLED = True  # Capture from both cameras simultaneously
    
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
        log_motor.info(f"Initializing motor controller (GPIO: PUL={CONFIG.GPIO_PULSE}, DIR={CONFIG.GPIO_DIRECTION}, ENA={CONFIG.GPIO_ENABLE})")
        self.pulse_pin = OutputDevice(CONFIG.GPIO_PULSE, initial_value=False)
        self.direction_pin = OutputDevice(CONFIG.GPIO_DIRECTION, initial_value=False)
        self.enable_pin = OutputDevice(CONFIG.GPIO_ENABLE, initial_value=True)  # HIGH = disabled
        log_motor.info("Motor controller initialized")
    
    def enable(self):
        """Enable motor driver (ENA is active LOW on DM556)."""
        self.enable_pin.off()  # LOW = enabled
        self.is_enabled = True
        time.sleep(0.01)
    
    def disable(self):
        """Disable motor driver."""
        self.enable_pin.on()  # HIGH = disabled
        self.is_enabled = False
    
    def step(self, num_steps, delay_ms=None):
        """Execute step pulses.
        
        Args:
            num_steps: Number of step pulses to execute
            delay_ms: Pulse edge delay in milliseconds (default: CONFIG.PULSE_DELAY_MS)
                      Note: Python sleep has ~1ms granularity; sub-ms values are approximate
        """
        if delay_ms is None:
            delay_ms = CONFIG.PULSE_DELAY_MS
        delay_s = delay_ms / 1000.0
        step_delay_s = CONFIG.STEP_DELAY_MS / 1000.0
        for _ in range(num_steps):
            self.pulse_pin.on()
            time.sleep(delay_s)
            self.pulse_pin.off()
            time.sleep(delay_s)
            time.sleep(step_delay_s)
    
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
# USB CAMERA CONTROLLER (Logitech BRIO / UVC cameras)
# =============================================================================
class USBCameraController:
    """Controller for USB webcams (Logitech BRIO, etc.) via OpenCV.
    
    NOTE: Preview is disabled by default when running alongside Picamera2
    to avoid Qt/threading conflicts that cause segmentation faults.
    """
    
    PREVIEW_WINDOW = "USB Camera Preview - Press Q to close"
    
    def __init__(self, camera_index=None, enable_preview=True):
        self.camera = None
        self.camera_index = camera_index
        self.is_initialized = False
        self.preview_active = False
        self.preview_thread = None
        self.stop_preview_flag = False
        self._cleanup_lock = threading.Lock()
        self._preview_enabled = enable_preview  # Can disable to avoid Qt conflicts
        self._capture_thread = None
        self._stop_capture_flag = False
        
        # Video recording state
        self.video_writer = None
        self.video_recording = False
        self.video_frame_count = 0
        self.current_angle = 0
        self.last_frame = None  # Store last frame for capture
        self._frame_lock = threading.Lock()
        
        if CV2_AVAILABLE and CONFIG.USB_CAMERA_ENABLED:
            self._initialize()
    
    def _find_usb_camera(self):
        """Find USB camera index by scanning available devices."""
        # Try the configured index first
        if self.camera_index is not None:
            cap = cv2.VideoCapture(self.camera_index)
            if cap.isOpened():
                cap.release()
                return self.camera_index
        
        # Scan for USB cameras (typically higher indices than CSI)
        # On Pi with CSI camera, USB cameras often start at index 2 or higher
        for idx in [0, 1, 2, 3, 4, 8, 10]:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                # Check if this looks like a USB camera (not CSI)
                # USB cameras typically support MJPG or YUYV
                backend = cap.getBackendName()
                log_camera.debug(f"Found camera at index {idx}, backend: {backend}")
                cap.release()
                # Skip low indices if we have CSI camera (those are usually CSI)
                if idx >= 2 or not CAMERA_AVAILABLE:
                    return idx
            cap.release()
        return None
    
    def _initialize(self):
        """Initialize USB camera."""
        try:
            # Find the camera
            idx = self._find_usb_camera()
            if idx is None:
                log_camera.warning("No USB camera found")
                return
            
            self.camera_index = idx
            log_camera.info(f"Initializing USB camera at index {idx}")
            
            self.camera = cv2.VideoCapture(idx)
            if not self.camera.isOpened():
                log_camera.error(f"Failed to open USB camera at index {idx}")
                self.camera = None
                return
            
            # Set resolution
            w, h = CONFIG.USB_CAMERA_RESOLUTION
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            
            # Get actual resolution
            actual_w = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            self.is_initialized = True
            log_camera.info(f"USB camera initialized: index={idx}, resolution={actual_w}x{actual_h}")
            print(f"  [USB CAM] Initialized at index {idx} ({actual_w}x{actual_h})")
            
        except Exception as e:
            log_camera.exception(f"USB camera initialization failed: {e}")
            print(f"  [USB CAM] Init failed: {e}")
            self.camera = None
    
    def start_preview(self):
        """Start live preview or background capture thread.
        
        If _preview_enabled is False, starts a background capture thread
        instead of showing a preview window (avoids Qt conflicts with Picamera2).
        """
        if not self.is_initialized:
            return False
        
        self.stop_preview_flag = False
        self._stop_capture_flag = False
        
        if self._preview_enabled:
            # Full preview with window (only use when USB camera is alone)
            self.preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
            self.preview_thread.start()
            self.preview_active = True
            return True
        else:
            # Background capture only (no window - safe with Picamera2)
            self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._capture_thread.start()
            self.preview_active = True  # Indicates capture is active
            log_camera.info("USB camera running in background capture mode (no preview)")
            return True
    
    def _capture_loop(self):
        """Background capture loop without preview window."""
        while not self._stop_capture_flag:
            try:
                ret, frame = self.camera.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue
                
                with self._frame_lock:
                    self.last_frame = frame.copy()
                
                # Record if active
                if self.video_recording and self.video_writer:
                    self.video_writer.write(frame)
                    self.video_frame_count += 1
                
                time.sleep(0.033)  # ~30fps capture rate
                    
            except Exception as e:
                log_camera.error(f"USB capture error: {e}")
                break
    
    def _preview_loop(self):
        """Preview loop for USB camera with window."""
        try:
            cv2.namedWindow(self.PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.PREVIEW_WINDOW, 640, 480)
        except Exception as e:
            log_camera.error(f"Failed to create USB preview window: {e}")
            return
        
        while not self.stop_preview_flag:
            try:
                ret, frame = self.camera.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue
                
                with self._frame_lock:
                    self.last_frame = frame.copy()
                
                # Record if active
                if self.video_recording and self.video_writer:
                    self.video_writer.write(frame)
                    self.video_frame_count += 1
                
                # Resize for preview
                preview = cv2.resize(frame, CONFIG.USB_CAMERA_PREVIEW_SIZE)
                cv2.imshow(self.PREVIEW_WINDOW, preview)
                
                if cv2.waitKey(16) & 0xFF == ord('q'):
                    break
                    
            except Exception as e:
                log_camera.error(f"USB preview error: {e}")
                break
        
        try:
            cv2.destroyWindow(self.PREVIEW_WINDOW)
            cv2.waitKey(1)
        except:
            pass
    
    def stop_preview(self):
        """Stop preview or background capture."""
        self.stop_preview_flag = True
        self._stop_capture_flag = True
        
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=2.0)
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)
        
        self.preview_active = False
        self.preview_thread = None
        self._capture_thread = None
    
    def capture(self, filepath, angle=None):
        """Capture and save image."""
        if not self.is_initialized:
            return False
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Use last captured frame or grab new one
            frame = None
            with self._frame_lock:
                if self.last_frame is not None:
                    frame = self.last_frame.copy()
            
            if frame is None:
                # Try direct capture
                ret, frame = self.camera.read()
                if not ret or frame is None:
                    log_camera.error("USB camera: failed to capture frame")
                    return False
            
            # Save image
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, CONFIG.CAMERA_QUALITY])
            
            if os.path.exists(filepath):
                log_camera.debug(f"USB cam captured: {os.path.basename(filepath)}")
                return True
            return False
        except Exception as e:
            log_camera.exception(f"USB capture error: {e}")
            return False
    
    def start_video_recording(self, filepath):
        """Start video recording."""
        if not self.is_initialized:
            return False
        try:
            fourcc = cv2.VideoWriter_fourcc(*CONFIG.VIDEO_CODEC)
            w, h = CONFIG.USB_CAMERA_RESOLUTION
            self.video_writer = cv2.VideoWriter(filepath, fourcc, CONFIG.VIDEO_FPS, (w, h))
            if self.video_writer.isOpened():
                self.video_recording = True
                self.video_frame_count = 0
                return True
            return False
        except:
            return False
    
    def stop_video_recording(self):
        """Stop video recording."""
        self.video_recording = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
    
    def set_current_angle(self, angle):
        self.current_angle = angle
    
    def get_status(self):
        if not self.is_initialized:
            return "NOT AVAILABLE"
        return f"USB Cam idx={self.camera_index}"
    
    def cleanup(self):
        """Release camera resources."""
        with self._cleanup_lock:
            log_camera.info("Cleaning up USB camera")
            self.stop_video_recording()
            self.stop_preview()  # This also stops _capture_thread
            
            if self.camera:
                try:
                    self.camera.release()
                except:
                    pass
                self.camera = None
            
            self.is_initialized = False
            with self._frame_lock:
                self.last_frame = None
            
            gc.collect()
            time.sleep(0.2)
            log_camera.info("USB camera cleanup complete")


# =============================================================================
# PI CAMERA CONTROLLER (CSI - Camera Module V3)
# =============================================================================
class PiCameraController:
    """Pi Camera Module V3 controller with live preview via OpenCV."""
    
    PREVIEW_WINDOW = "Pi Camera Preview - Press Q to close"
    
    # Overlay settings
    OVERLAY_FONT = cv2.FONT_HERSHEY_SIMPLEX if CV2_AVAILABLE else None
    OVERLAY_FONT_SCALE_PREVIEW = 1.5
    OVERLAY_FONT_SCALE_STILL = 4.0
    OVERLAY_COLOR = (255, 255, 255)  # White
    OVERLAY_SHADOW_COLOR = (0, 0, 0)  # Black shadow for readability
    OVERLAY_THICKNESS_PREVIEW = 2
    OVERLAY_THICKNESS_STILL = 8
    
    def __init__(self):
        self.camera = None
        self.is_initialized = False
        self.preview_active = False
        self.preview_thread = None
        self.stop_preview_flag = False
        self._cleanup_lock = threading.Lock()  # Prevent concurrent cleanup/init
        
        # Video recording state
        self.video_writer = None
        self.video_recording = False
        self.video_frame_count = 0
        self.current_angle = 0
        
        if CAMERA_AVAILABLE:
            self._initialize()
    
    def _initialize(self):
        try:
            log_camera.info("Initializing Picamera2")
            self.camera = Picamera2()
            # Single configuration with both streams from SAME sensor mode:
            # - main: full resolution for capture (what you save)
            # - lores: scaled down for preview (exact same framing/colors)
            # Using RGB888 format - Picamera2 outputs RGB regardless of BGR888 setting
            # OpenCV conversion to BGR is done in preview loop
            config = self.camera.create_still_configuration(
                main={"size": CONFIG.CAMERA_RESOLUTION, "format": "RGB888"},
                lores={"size": CONFIG.CAMERA_PREVIEW_SIZE, "format": "RGB888"},
                buffer_count=4,
                queue=True,  # Enable frame queueing for smoother preview
            )
            self.camera.configure(config)
            self.camera.set_controls({
                "AfMode": controls.AfModeEnum.Continuous,
                "AfSpeed": controls.AfSpeedEnum.Normal,
                "AwbEnable": True,
            })
            self.camera.start()
            # Wait for AWB/AEC to stabilize
            print("  [CAMERA] Waiting for auto-exposure to stabilize...")
            time.sleep(2)
            self.is_initialized = True
            log_camera.info(f"Camera initialized (resolution={CONFIG.CAMERA_RESOLUTION}, preview={CONFIG.CAMERA_PREVIEW_SIZE})")
        except Exception as e:
            log_camera.exception(f"Camera initialization failed: {e}")
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
        try:
            # Destroy any stale window with same name first
            cv2.destroyWindow(self.PREVIEW_WINDOW)
            cv2.waitKey(1)
        except Exception:
            pass
        
        try:
            cv2.namedWindow(self.PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.PREVIEW_WINDOW, 800, 600)
            cv2.waitKey(1)  # Flush window creation
        except Exception as e:
            print(f"  [CAMERA] Failed to create preview window: {e}")
            return
        
        frame_count = 0
        error_count = 0
        max_errors = 10  # Stop after consecutive errors
        
        while not self.stop_preview_flag:
            try:
                # Capture from lores stream - same framing as main, just scaled down
                frame = self.camera.capture_array("lores")
                
                if frame is None:
                    error_count += 1
                    log_camera.warning(f"Frame capture returned None (error {error_count}/{max_errors})")
                    if error_count >= max_errors:
                        log_camera.error("Too many frame errors, stopping preview")
                        print(f"\n  [CAMERA] Too many frame errors, stopping preview")
                        break
                    continue
                
                # Picamera2 outputs RGB, OpenCV expects BGR
                # If colors look wrong in preview, toggle CONFIG.PREVIEW_SWAP_RB
                if CONFIG.PREVIEW_SWAP_RB:
                    frame_bgr = frame  # Don't convert - already in correct format
                else:
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                error_count = 0  # Reset on successful frame
                frame_count += 1
                
                # Record frame to video if recording is active
                if self.video_recording:
                    self.record_frame(frame_bgr)
                
                # Add angle overlay to preview display
                display_frame = self.add_angle_overlay(frame_bgr.copy(), self.current_angle, is_still=False)
                cv2.imshow(self.PREVIEW_WINDOW, display_frame)
                
                # 16ms = ~60fps max, but actual fps limited by camera
                key = cv2.waitKey(16) & 0xFF
                if key == ord('q'):
                    break
                    
            except Exception as e:
                error_count += 1
                if error_count >= max_errors:
                    print(f"\n  [CAMERA] Preview error: {e}")
                    break
                time.sleep(0.1)  # Brief pause before retry
        
        # Properly destroy window and flush event queue
        try:
            cv2.destroyWindow(self.PREVIEW_WINDOW)
            cv2.waitKey(1)
            cv2.destroyAllWindows()
            cv2.waitKey(1)
        except Exception:
            pass
    
    def _start_native_preview(self):
        """Start preview using Picamera2 native preview."""
        # Native preview requires Qt/GTK event loop which conflicts with terminal apps
        # This is a fallback only - OpenCV preview is preferred
        preview_types = []
        if Preview is not None:
            preview_types = [
                ("DRM", getattr(Preview, "DRM", None)),      # Direct rendering - no event loop needed
                ("QT", getattr(Preview, "QT", None)),        # Qt-based
                ("QTGL", getattr(Preview, "QTGL", None)),    # Qt OpenGL
            ]
        
        for name, preview_type in preview_types:
            if preview_type is None:
                continue
            try:
                self.camera.start_preview(preview_type, x=100, y=100, width=800, height=600)
                self.preview_active = True
                return True
            except RuntimeError as e:
                if "event loop" in str(e).lower():
                    # Event loop conflict - skip all Qt-based previews
                    print(f"  [CAMERA] {name} preview skipped: event loop conflict")
                    if name in ("QT", "QTGL"):
                        continue
                continue
            except Exception:
                continue
        
        # All previews failed
        print("  [CAMERA] Preview window not available - running without preview")
        return False
    
    def stop_preview(self):
        """Stop live video preview."""
        self.stop_preview_flag = True
        
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=2.0)
        
        if CV2_AVAILABLE:
            try:
                # Destroy specific window and flush event queue
                cv2.destroyWindow(self.PREVIEW_WINDOW)
                cv2.waitKey(1)
                cv2.destroyAllWindows()
                # Multiple waitKey calls to ensure event loop processes destruction
                for _ in range(5):
                    cv2.waitKey(1)
            except Exception:
                pass
        
        if self.preview_active and self.camera:
            try:
                self.camera.stop_preview()
            except Exception:
                pass
        
        self.preview_active = False
        self.preview_thread = None
    
    def capture(self, filepath, angle=None):
        """Capture and save a high-resolution image with angle overlay."""
        if not CAMERA_AVAILABLE:
            return self._mock_capture(filepath, angle)
        if not self.is_initialized:
            log_camera.error("Capture attempted but camera not initialized")
            return False
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            # Trigger autofocus
            self.camera.set_controls({"AfTrigger": controls.AfTriggerEnum.Start})
            time.sleep(0.3)
            # Direct capture from main stream - same config as preview, just full resolution
            self.camera.capture_file(filepath, name="main")
            
            # Add angle overlay to saved image
            if angle is not None and CV2_AVAILABLE and os.path.exists(filepath):
                self._add_overlay_to_file(filepath, angle)
            
            if os.path.exists(filepath):
                size_kb = os.path.getsize(filepath) / 1024
                log_camera.debug(f"Captured: {os.path.basename(filepath)} ({size_kb:.0f}KB)")
                return True
            log_camera.error(f"Capture file not created: {filepath}")
            return False
        except Exception as e:
            log_camera.exception(f"Capture error: {e}")
            print(f"  [CAMERA] Capture error: {e}")
            return False
    
    def _add_overlay_to_file(self, filepath, angle):
        """Add angle overlay to an existing image file."""
        try:
            img = cv2.imread(filepath)
            if img is not None:
                img = self.add_angle_overlay(img, angle, is_still=True)
                cv2.imwrite(filepath, img, [cv2.IMWRITE_JPEG_QUALITY, CONFIG.CAMERA_QUALITY])
        except Exception as e:
            print(f"  [CAMERA] Overlay error: {e}")
    
    def _mock_capture(self, filepath, angle=None):
        """Create mock image for testing without camera."""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            if PIL_AVAILABLE:
                img = Image.new('RGB', (640, 480), color='white')
                img.save(filepath, 'JPEG', quality=CONFIG.CAMERA_QUALITY)
                # Add overlay if angle provided and OpenCV available
                if angle is not None and CV2_AVAILABLE:
                    self._add_overlay_to_file(filepath, angle)
            else:
                with open(filepath, 'w') as f:
                    f.write("MOCK")
            return True
        except Exception:
            return False
    
    def set_current_angle(self, angle):
        """Set current angle for video overlay."""
        self.current_angle = angle
    
    def add_angle_overlay(self, frame, angle, is_still=False):
        """Add angle text overlay to top-right corner of frame."""
        if not CV2_AVAILABLE or frame is None:
            return frame
        
        text = f"{int(angle):03d} deg"
        font_scale = self.OVERLAY_FONT_SCALE_STILL if is_still else self.OVERLAY_FONT_SCALE_PREVIEW
        thickness = self.OVERLAY_THICKNESS_STILL if is_still else self.OVERLAY_THICKNESS_PREVIEW
        
        # Get text size to position in top-right
        (text_w, text_h), baseline = cv2.getTextSize(text, self.OVERLAY_FONT, font_scale, thickness)
        
        # Position: top-right with padding
        padding = 20 if not is_still else 60
        x = frame.shape[1] - text_w - padding
        y = text_h + padding
        
        # Draw shadow for readability
        cv2.putText(frame, text, (x + 2, y + 2), self.OVERLAY_FONT, font_scale, 
                    self.OVERLAY_SHADOW_COLOR, thickness + 2, cv2.LINE_AA)
        # Draw main text
        cv2.putText(frame, text, (x, y), self.OVERLAY_FONT, font_scale,
                    self.OVERLAY_COLOR, thickness, cv2.LINE_AA)
        
        return frame
    
    def start_video_recording(self, filepath):
        """Start recording video to file.
        
        Video is recorded at preview resolution (CONFIG.CAMERA_PREVIEW_SIZE) for performance.
        Full resolution stills are captured separately during the scan.
        
        Codec priority: CONFIG.VIDEO_CODEC first, then fallbacks for compatibility.
        """
        if not CV2_AVAILABLE:
            log_camera.warning("OpenCV not available, video recording disabled")
            return False
        try:
            # Try configured codec first, then fallbacks
            preferred = CONFIG.VIDEO_CODEC
            fallbacks = ['mp4v', 'avc1', 'XVID', 'MJPG']
            codecs = [preferred] + [c for c in fallbacks if c != preferred]
            
            fps = CONFIG.VIDEO_FPS
            # Video recorded at preview resolution for performance (not capture resolution)
            frame_size = (CONFIG.CAMERA_PREVIEW_SIZE[0], CONFIG.CAMERA_PREVIEW_SIZE[1])
            
            for codec in codecs:
                fourcc = cv2.VideoWriter_fourcc(*codec)
                self.video_writer = cv2.VideoWriter(filepath, fourcc, fps, frame_size)
                if self.video_writer.isOpened():
                    self.video_recording = True
                    self.video_frame_count = 0
                    log_camera.info(f"Video recording started: {filepath} (codec={codec}, {frame_size[0]}x{frame_size[1]}@{fps}fps)")
                    print(f"  [VIDEO] Recording at {frame_size[0]}x{frame_size[1]} using codec: {codec}")
                    return True
                self.video_writer.release()
                log_camera.debug(f"Codec {codec} failed, trying next")
            
            log_camera.error("No compatible video codec found")
            print("  [VIDEO] No compatible codec found")
            self.video_writer = None
            return False
        except Exception as e:
            log_camera.exception(f"Failed to start video recording: {e}")
            print(f"  [VIDEO] Failed to start recording: {e}")
            return False
    
    def record_frame(self, frame):
        """Record a single frame with angle overlay to video."""
        if not self.video_recording or self.video_writer is None:
            return
        if not self.video_writer.isOpened():
            return
        try:
            # Verify frame dimensions match expected size
            h, w = frame.shape[:2]
            expected_w, expected_h = CONFIG.CAMERA_PREVIEW_SIZE
            if w != expected_w or h != expected_h:
                frame = cv2.resize(frame, (expected_w, expected_h))
            
            # Add angle overlay
            frame_with_overlay = self.add_angle_overlay(frame.copy(), self.current_angle, is_still=False)
            self.video_writer.write(frame_with_overlay)
            self.video_frame_count += 1
        except Exception as e:
            pass
    
    def stop_video_recording(self):
        """Stop video recording and release writer."""
        was_recording = self.video_recording
        frame_count = getattr(self, 'video_frame_count', 0)
        self.video_recording = False
        if self.video_writer is not None:
            try:
                self.video_writer.release()
            except Exception:
                pass
            self.video_writer = None
        if was_recording:
            print(f"  [VIDEO] Recorded {frame_count} frames")
    
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
        """Clean up camera resources - must fully release for re-initialization.
        
        Thread-safe cleanup with lock to prevent race conditions during
        concurrent cleanup/initialization attempts.
        """
        with self._cleanup_lock:
            log_camera.info("Starting Pi camera cleanup")
            
            # Stop video recording first
            self.stop_video_recording()
            
            # Stop preview and wait for thread to fully terminate
            self.stop_preview()
            
            # Wait for preview thread to fully terminate
            if self.preview_thread is not None:
                self.preview_thread.join(timeout=3.0)
                if self.preview_thread.is_alive():
                    log_camera.warning("Preview thread did not terminate cleanly")
            
            # Fully release camera with explicit stop -> close sequence
            if self.camera:
                try:
                    self.camera.stop()
                    log_camera.debug("Camera stopped")
                except Exception as e:
                    log_camera.debug(f"Camera stop exception (may be expected): {e}")
                
                # Small delay between stop and close
                time.sleep(0.1)
                
                try:
                    self.camera.close()
                    log_camera.debug("Camera closed")
                except Exception as e:
                    log_camera.debug(f"Camera close exception (may be expected): {e}")
                self.camera = None
            
            # Reset all state
            self.is_initialized = False
            self.preview_active = False
            self.preview_thread = None
            self.stop_preview_flag = False
            self.video_writer = None
            self.video_recording = False
            self.video_frame_count = 0
            self.current_angle = 0
            
            # Force garbage collection multiple times to ensure cleanup
            gc.collect()
            time.sleep(0.2)
            gc.collect()
            
            # Allow hardware to fully release before potential re-init
            # This longer delay is necessary for libcamera to release /dev/video* handles
            time.sleep(0.5)
            log_camera.info("Pi camera cleanup complete")
    
    @staticmethod
    def is_camera_available():
        """Check if Pi camera hardware is available and not in use."""
        if not CAMERA_AVAILABLE:
            return False
        try:
            # Try to create a temporary Picamera2 instance
            test_cam = Picamera2()
            test_cam.close()
            del test_cam
            gc.collect()
            time.sleep(0.1)
            return True
        except Exception as e:
            log_camera.debug(f"Camera availability check failed: {e}")
            return False

# Backward compatibility alias
CameraController = PiCameraController


# =============================================================================
# DUAL CAMERA MANAGER
# =============================================================================
class DualCameraManager:
    """Manages both Pi Camera and USB camera simultaneously.
    
    Uses a COMBINED side-by-side preview window to show both cameras
    without Qt/threading conflicts. Both camera feeds are displayed
    in a single OpenCV window.
    """
    
    PREVIEW_WINDOW = "Dual Camera Preview - Press Q to close"
    
    def __init__(self):
        self.pi_camera = None
        self.usb_camera = None
        self.is_initialized = False
        self.preview_active = False
        self.preview_thread = None
        self.stop_preview_flag = False
        self._cleanup_lock = threading.Lock()
        
        # Frame storage for combined preview
        self._pi_frame = None
        self._usb_frame = None
        self._frame_lock = threading.Lock()
        
        # Video recording
        self.pi_video_writer = None
        self.usb_video_writer = None
        self.video_recording = False
        self.current_angle = 0
        
        log_camera.info("Initializing DualCameraManager")
        
        # Initialize Pi Camera (CSI) - but DON'T start its own preview
        if CAMERA_AVAILABLE:
            self.pi_camera = PiCameraController()
            if not self.pi_camera.is_initialized:
                log_camera.warning("Pi camera initialization failed")
                self.pi_camera = None
        
        # Initialize USB Camera - DON'T start its own preview either
        if CV2_AVAILABLE and CONFIG.USB_CAMERA_ENABLED:
            # Disable individual preview - we'll use combined preview
            self.usb_camera = USBCameraController(enable_preview=False)
            if not self.usb_camera.is_initialized:
                log_camera.warning("USB camera initialization failed")
                self.usb_camera = None
        
        self.is_initialized = (self.pi_camera is not None) or (self.usb_camera is not None)
        
        if self.is_initialized:
            cams = []
            if self.pi_camera:
                cams.append("Pi Camera V3")
            if self.usb_camera:
                cams.append("USB Camera")
            log_camera.info(f"DualCameraManager ready with: {', '.join(cams)}")
    
    def start_preview(self):
        """Start combined side-by-side preview for both cameras."""
        if not self.is_initialized or not CV2_AVAILABLE:
            return False
        
        self.stop_preview_flag = False
        
        # Start USB camera background capture (no window)
        if self.usb_camera:
            self.usb_camera.start_preview()  # This starts _capture_loop since preview is disabled
        
        # Start combined preview thread
        self.preview_thread = threading.Thread(target=self._combined_preview_loop, daemon=True)
        self.preview_thread.start()
        self.preview_active = True
        return True
    
    def _combined_preview_loop(self):
        """Combined preview showing both cameras side-by-side in ONE window."""
        try:
            cv2.namedWindow(self.PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.PREVIEW_WINDOW, 1280, 480)  # Side by side
        except Exception as e:
            log_camera.error(f"Failed to create combined preview window: {e}")
            return
        
        preview_w, preview_h = 640, 480  # Size for each camera in combined view
        
        while not self.stop_preview_flag:
            try:
                pi_frame = None
                usb_frame = None
                
                # Get Pi Camera frame
                if self.pi_camera and self.pi_camera.is_initialized and self.pi_camera.camera:
                    try:
                        frame = self.pi_camera.camera.capture_array("lores")
                        if frame is not None:
                            # Convert RGB to BGR for OpenCV
                            if CONFIG.PREVIEW_SWAP_RB:
                                pi_frame = frame
                            else:
                                pi_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                            pi_frame = cv2.resize(pi_frame, (preview_w, preview_h))
                            
                            # Store for capture
                            with self._frame_lock:
                                self._pi_frame = pi_frame.copy()
                            
                            # Record to video if active
                            if self.video_recording and self.pi_video_writer:
                                self.pi_video_writer.write(pi_frame)
                    except Exception as e:
                        log_camera.debug(f"Pi frame capture error: {e}")
                
                # Get USB Camera frame
                if self.usb_camera and self.usb_camera.is_initialized:
                    with self.usb_camera._frame_lock:
                        if self.usb_camera.last_frame is not None:
                            usb_frame = cv2.resize(self.usb_camera.last_frame.copy(), (preview_w, preview_h))
                            
                            # Store for capture
                            with self._frame_lock:
                                self._usb_frame = usb_frame.copy()
                            
                            # Record to video if active
                            if self.video_recording and self.usb_video_writer:
                                self.usb_video_writer.write(usb_frame)
                
                # Create combined frame
                if pi_frame is not None and usb_frame is not None:
                    # Both cameras - side by side
                    combined = cv2.hconcat([pi_frame, usb_frame])
                    # Add labels
                    cv2.putText(combined, "Pi Camera V3", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                               1, (0, 255, 0), 2, cv2.LINE_AA)
                    cv2.putText(combined, "USB Camera", (preview_w + 10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                               1, (0, 255, 0), 2, cv2.LINE_AA)
                elif pi_frame is not None:
                    combined = pi_frame
                    cv2.putText(combined, "Pi Camera V3", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                               1, (0, 255, 0), 2, cv2.LINE_AA)
                elif usb_frame is not None:
                    combined = usb_frame
                    cv2.putText(combined, "USB Camera", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                               1, (0, 255, 0), 2, cv2.LINE_AA)
                else:
                    # No frames - create blank
                    combined = cv2.imread.__self__  # Placeholder, will skip
                    time.sleep(0.05)
                    continue
                
                # Add angle overlay
                angle_text = f"Angle: {int(self.current_angle):03d} deg"
                cv2.putText(combined, angle_text, (combined.shape[1] - 200, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
                
                cv2.imshow(self.PREVIEW_WINDOW, combined)
                
                if cv2.waitKey(16) & 0xFF == ord('q'):
                    break
                    
            except Exception as e:
                log_camera.error(f"Combined preview error: {e}")
                time.sleep(0.1)
        
        try:
            cv2.destroyWindow(self.PREVIEW_WINDOW)
            cv2.waitKey(1)
            cv2.destroyAllWindows()
            cv2.waitKey(1)
        except:
            pass
    
    def stop_preview(self):
        """Stop combined preview."""
        self.stop_preview_flag = True
        
        # Stop USB camera capture thread
        if self.usb_camera:
            self.usb_camera.stop_preview()
        
        # Wait for combined preview thread
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=2.0)
        
        self.preview_active = False
        self.preview_thread = None
    
    def capture(self, pi_filepath, usb_filepath=None, angle=None):
        """Capture from both cameras.
        
        Returns: (pi_success, usb_success)
        """
        pi_ok = False
        usb_ok = False
        
        # Capture from Pi camera
        if self.pi_camera and pi_filepath:
            pi_ok = self.pi_camera.capture(pi_filepath, angle)
        
        # Capture from USB camera
        if self.usb_camera and usb_filepath:
            usb_ok = self.usb_camera.capture(usb_filepath, angle)
        
        return pi_ok, usb_ok
    
    def start_video_recording(self, pi_filepath, usb_filepath=None):
        """Start video recording on both cameras."""
        pi_ok = False
        usb_ok = False
        
        preview_size = (640, 480)  # Match combined preview size
        fps = CONFIG.VIDEO_FPS
        
        if pi_filepath:
            try:
                fourcc = cv2.VideoWriter_fourcc(*CONFIG.VIDEO_CODEC)
                self.pi_video_writer = cv2.VideoWriter(pi_filepath, fourcc, fps, preview_size)
                pi_ok = self.pi_video_writer.isOpened()
                if pi_ok:
                    log_camera.info(f"Pi video recording started: {pi_filepath}")
            except Exception as e:
                log_camera.error(f"Failed to start Pi video: {e}")
        
        if usb_filepath:
            try:
                fourcc = cv2.VideoWriter_fourcc(*CONFIG.VIDEO_CODEC)
                self.usb_video_writer = cv2.VideoWriter(usb_filepath, fourcc, fps, preview_size)
                usb_ok = self.usb_video_writer.isOpened()
                if usb_ok:
                    log_camera.info(f"USB video recording started: {usb_filepath}")
            except Exception as e:
                log_camera.error(f"Failed to start USB video: {e}")
        
        self.video_recording = pi_ok or usb_ok
        return pi_ok, usb_ok
    
    def stop_video_recording(self):
        """Stop video recording on both cameras."""
        self.video_recording = False
        
        if self.pi_video_writer:
            try:
                self.pi_video_writer.release()
            except:
                pass
            self.pi_video_writer = None
        
        if self.usb_video_writer:
            try:
                self.usb_video_writer.release()
            except:
                pass
            self.usb_video_writer = None
    
    def set_current_angle(self, angle):
        """Set angle for overlay."""
        self.current_angle = angle
        if self.pi_camera:
            self.pi_camera.set_current_angle(angle)
        if self.usb_camera:
            self.usb_camera.set_current_angle(angle)
    
    def get_status(self):
        """Get combined status."""
        status = []
        if self.pi_camera and self.pi_camera.is_initialized:
            status.append(f"Pi: {self.pi_camera.get_status()}")
        if self.usb_camera and self.usb_camera.is_initialized:
            status.append("USB: Active")
        return " | ".join(status) if status else "No cameras"
    
    def cleanup(self):
        """Cleanup both cameras and preview."""
        with self._cleanup_lock:
            log_camera.info("Cleaning up DualCameraManager")
            
            # Stop video recording
            self.stop_video_recording()
            
            # Stop combined preview
            self.stop_preview()
            
            # Cleanup individual cameras
            if self.pi_camera:
                self.pi_camera.cleanup()
                self.pi_camera = None
            
            if self.usb_camera:
                self.usb_camera.cleanup()
                self.usb_camera = None
            
            # Clear frame storage
            with self._frame_lock:
                self._pi_frame = None
                self._usb_frame = None
            
            self.is_initialized = False
            gc.collect()
            time.sleep(0.3)
            log_camera.info("DualCameraManager cleanup complete")


# =============================================================================
# CAMERA SETTINGS CONTROLLER (Pi Camera V3 real-time adjustments)
# =============================================================================
class CameraSettingsController:
    """Real-time camera settings adjustment with live preview for Pi Camera V3."""
    
    # Available controls for IMX708 (Pi Camera V3)
    CONTROLS = {
        'focus': {
            'name': 'Manual Focus',
            'control': 'LensPosition',
            'min': 0.0,
            'max': 15.0,
            'step': 0.5,
            'default': 1.0,
            'unit': 'diopters (0=inf, 15=macro)'
        },
        'exposure': {
            'name': 'Exposure Time',
            'control': 'ExposureTime',
            'min': 100,
            'max': 1000000,
            'step': 1000,
            'default': 20000,
            'unit': 'microseconds'
        },
        'gain': {
            'name': 'Analogue Gain',
            'control': 'AnalogueGain',
            'min': 1.0,
            'max': 16.0,
            'step': 0.5,
            'default': 1.0,
            'unit': 'x'
        },
        'brightness': {
            'name': 'Brightness',
            'control': 'Brightness',
            'min': -1.0,
            'max': 1.0,
            'step': 0.1,
            'default': 0.0,
            'unit': ''
        },
        'contrast': {
            'name': 'Contrast',
            'control': 'Contrast',
            'min': 0.0,
            'max': 2.0,
            'step': 0.1,
            'default': 1.0,
            'unit': ''
        },
        'saturation': {
            'name': 'Saturation',
            'control': 'Saturation',
            'min': 0.0,
            'max': 2.0,
            'step': 0.1,
            'default': 1.0,
            'unit': ''
        },
        'sharpness': {
            'name': 'Sharpness',
            'control': 'Sharpness',
            'min': 0.0,
            'max': 16.0,
            'step': 1.0,
            'default': 1.0,
            'unit': ''
        },
    }
    
    def __init__(self, pi_camera):
        """Initialize with a PiCameraController instance."""
        self.pi_camera = pi_camera
        self.current_values = {}
        self.af_mode = 'continuous'  # 'continuous', 'manual', 'auto'
        
        # Initialize current values from defaults
        for key, ctrl in self.CONTROLS.items():
            self.current_values[key] = ctrl['default']
    
    def set_af_mode(self, mode):
        """Set autofocus mode: 'continuous', 'manual', or 'auto'."""
        if not self.pi_camera or not self.pi_camera.camera:
            return False
        
        try:
            if mode == 'continuous':
                self.pi_camera.camera.set_controls({
                    "AfMode": controls.AfModeEnum.Continuous,
                    "AfSpeed": controls.AfSpeedEnum.Normal,
                })
            elif mode == 'manual':
                self.pi_camera.camera.set_controls({
                    "AfMode": controls.AfModeEnum.Manual,
                })
            elif mode == 'auto':
                self.pi_camera.camera.set_controls({
                    "AfMode": controls.AfModeEnum.Auto,
                })
                # Trigger single autofocus
                self.pi_camera.camera.set_controls({
                    "AfTrigger": controls.AfTriggerEnum.Start,
                })
            
            self.af_mode = mode
            log_camera.info(f"AF mode set to: {mode}")
            return True
        except Exception as e:
            log_camera.error(f"Failed to set AF mode: {e}")
            return False
    
    def set_control(self, key, value):
        """Set a camera control value."""
        if key not in self.CONTROLS:
            return False
        if not self.pi_camera or not self.pi_camera.camera:
            return False
        
        ctrl = self.CONTROLS[key]
        # Clamp value to valid range
        value = max(ctrl['min'], min(ctrl['max'], value))
        
        try:
            # Special handling for focus (requires manual AF mode)
            if key == 'focus':
                if self.af_mode != 'manual':
                    self.set_af_mode('manual')
                    time.sleep(0.1)  # Give AF mode time to switch
                # LensPosition is set separately after AfMode is Manual
                self.pi_camera.camera.set_controls({"LensPosition": value})
                self.current_values[key] = value
                log_camera.info(f"Set focus (LensPosition) to {value}")
                return True
            
            self.pi_camera.camera.set_controls({ctrl['control']: value})
            self.current_values[key] = value
            log_camera.debug(f"Set {key} to {value}")
            return True
        except Exception as e:
            log_camera.error(f"Failed to set {key}: {e}")
            print(f"  Error setting {key}: {e}")
            return False
    
    def get_control(self, key):
        """Get current value of a control."""
        return self.current_values.get(key)
    
    def adjust_control(self, key, delta):
        """Adjust a control by delta amount."""
        if key not in self.CONTROLS:
            return False
        
        current = self.current_values.get(key, self.CONTROLS[key]['default'])
        new_value = current + delta
        return self.set_control(key, new_value)
    
    def reset_to_defaults(self):
        """Reset all controls to defaults."""
        for key, ctrl in self.CONTROLS.items():
            self.set_control(key, ctrl['default'])
        self.set_af_mode('continuous')
    
    def get_all_values(self):
        """Get dictionary of all current values."""
        return self.current_values.copy()


# =============================================================================
# STORAGE MANAGER
# =============================================================================
class StorageManager:
    def __init__(self):
        self.local_path = CONFIG.LOCAL_STORAGE_PATH
        self.current_piece_id = None
        self.current_folder = None
        self.pi_folder = None   # Subfolder for Pi camera images
        self.usb_folder = None  # Subfolder for USB camera images
        os.makedirs(self.local_path, exist_ok=True)
    
    def set_piece_id(self, piece_number, dual_camera=False):
        self.current_piece_id = CONFIG.PIECE_ID_FORMAT.format(int(piece_number))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_folder = os.path.join(self.local_path, f"{self.current_piece_id}_{timestamp}")
        os.makedirs(self.current_folder, exist_ok=True)
        
        # Create subfolders for dual camera mode
        if dual_camera and CONFIG.DUAL_CAMERA_ENABLED:
            self.pi_folder = os.path.join(self.current_folder, "pi_camera")
            self.usb_folder = os.path.join(self.current_folder, "usb_camera")
            os.makedirs(self.pi_folder, exist_ok=True)
            os.makedirs(self.usb_folder, exist_ok=True)
            log_storage.info(f"New dual-camera scan: piece_id={self.current_piece_id}")
        else:
            self.pi_folder = self.current_folder
            self.usb_folder = None
            log_storage.info(f"New scan: piece_id={self.current_piece_id}, folder={self.current_folder}")
        
        return self.current_piece_id
    
    def get_filepath(self, angle, camera='pi'):
        """Get filepath for image.
        
        Args:
            angle: Rotation angle
            camera: 'pi' for Pi camera, 'usb' for USB camera
        """
        if not self.current_piece_id:
            raise ValueError("Piece ID not set")
        
        folder = self.pi_folder if camera == 'pi' else self.usb_folder
        if folder is None:
            folder = self.current_folder
        
        cam_suffix = f"_{camera}" if self.usb_folder else ""
        filename = f"{CONFIG.FILE_PREFIX}_{self.current_piece_id}_{int(angle):03d}deg{cam_suffix}.{CONFIG.FILE_EXTENSION}"
        return os.path.join(folder, filename)
    
    def get_video_filepath(self, camera='pi'):
        """Get filepath for scan video."""
        if not self.current_piece_id:
            raise ValueError("Piece ID not set")
        
        folder = self.pi_folder if camera == 'pi' else self.usb_folder
        if folder is None:
            folder = self.current_folder
        
        cam_suffix = f"_{camera}" if self.usb_folder else ""
        filename = f"{CONFIG.FILE_PREFIX}_{self.current_piece_id}_scan{cam_suffix}.mp4"
        return os.path.join(folder, filename)
    
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
        """Display the persistent header with project title and license."""
        clear_screen()
        
        # Project title
        print(PROJECT_TITLE)
        
        # License text
        print(LICENSE_TEXT)
    
    def show_main_menu(self):
        """Display main menu options."""
        self.show_header()
        
        print("\n" + "=" * 100)
        print("                                      MAIN MENU")
        print("=" * 100)
        print(f"\n  Current Settings: Increment={CONFIG.ROTATION_INCREMENT}deg | Photos={CONFIG.TOTAL_PHOTOS} | Calibration={CONFIG.CALIBRATION_FACTOR:.4f}")
        print(f"  Storage: {CONFIG.LOCAL_STORAGE_PATH}")
        
        # Camera status
        cam_status = []
        if CAMERA_AVAILABLE:
            cam_status.append("Pi Cam V3")
        if CV2_AVAILABLE and CONFIG.USB_CAMERA_ENABLED:
            cam_status.append("USB Cam")
        dual_status = "ENABLED" if CONFIG.DUAL_CAMERA_ENABLED and len(cam_status) > 1 else "DISABLED"
        print(f"  Cameras: {', '.join(cam_status) if cam_status else 'None'} | Dual Mode: {dual_status}")
        
        print("\n" + "-" * 100)
        print("\n    [1] LAUNCH CAPTURE        Start 360 degree scan with live preview")
        print("    [2] TEST CAMERA           View continuous video feed (no saving)")
        print("    [3] TEST MOTOR            Motor control and calibration")
        print("    [4] CAMERA SETTINGS       Adjust focus, exposure, zoom (Pi Camera)")
        print("    [5] INFORMATION           Wiring diagram and documentation")
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
                self.camera_settings_menu()
            elif choice == "5":
                self.show_information()
            elif choice == "0":
                print("\n  Exiting. Goodbye.")
                break
    
    def launch_capture(self):
        """Run full 360 degree capture with live preview (supports dual camera)."""
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
        
        # Determine if using dual camera mode
        use_dual = CONFIG.DUAL_CAMERA_ENABLED and CONFIG.USB_CAMERA_ENABLED
        
        print("\n  Initializing hardware...")
        progress_bar(0, 4, "  Init")
        
        self.motor = MotorController()
        progress_bar(1, 4, "  Init")
        
        # Use DualCameraManager if dual mode, else single PiCameraController
        if use_dual:
            self.camera = DualCameraManager()
            print("\n  [DUAL CAM] Dual camera mode enabled")
        else:
            self.camera = PiCameraController()
        progress_bar(2, 4, "  Init")
        
        if not self.camera.is_initialized:
            print("\n  ERROR: No cameras initialized. Check connections.")
            input("\n  Press ENTER to continue...")
            return
        
        self.storage = StorageManager()
        piece_id = self.storage.set_piece_id(piece_number, dual_camera=use_dual)
        progress_bar(3, 4, "  Init")
        progress_bar(4, 4, "  Init")
        
        print(f"\n  Piece ID: {piece_id}")
        print(f"  Output: {self.storage.current_folder}")
        
        # Start live preview
        print("\n  Starting live preview...")
        preview_ok = self.camera.start_preview()
        if preview_ok:
            print("  [PREVIEW] Live video window(s) opened")
        else:
            print("  [PREVIEW] Running without preview window")
        
        # Start video recording
        if use_dual and isinstance(self.camera, DualCameraManager):
            pi_video = self.storage.get_video_filepath('pi')
            usb_video = self.storage.get_video_filepath('usb')
            pi_vid_ok, usb_vid_ok = self.camera.start_video_recording(pi_video, usb_video)
            video_ok = pi_vid_ok or usb_vid_ok
            if pi_vid_ok:
                print(f"  [VIDEO] Pi camera recording to: {os.path.basename(pi_video)}")
            if usb_vid_ok:
                print(f"  [VIDEO] USB camera recording to: {os.path.basename(usb_video)}")
        else:
            video_path = self.storage.get_video_filepath()
            video_ok = self.camera.start_video_recording(video_path) if hasattr(self.camera, 'start_video_recording') else False
            if video_ok:
                print(f"  [VIDEO] Recording to: {os.path.basename(video_path)}")
        
        if not video_ok:
            print("  [VIDEO] Video recording not available")
        
        print(f"\n  Starting scan... Press Ctrl+C to abort.\n")
        
        self.motor.enable()
        self.motor.reset_position()
        self.camera.set_current_angle(0)
        
        pi_captured = 0
        usb_captured = 0
        
        try:
            for i in range(CONFIG.TOTAL_PHOTOS):
                current_angle = i * CONFIG.ROTATION_INCREMENT
                
                # Update angle for video overlay
                self.camera.set_current_angle(current_angle)
                
                # Status update
                status = self.camera.get_status()
                print(f"  [{i+1:2d}/{CONFIG.TOTAL_PHOTOS}] Angle: {current_angle:03d}deg | {status}")
                
                time.sleep(CONFIG.CAPTURE_DELAY)
                
                # Capture from both cameras
                if use_dual and isinstance(self.camera, DualCameraManager):
                    pi_path = self.storage.get_filepath(current_angle, 'pi')
                    usb_path = self.storage.get_filepath(current_angle, 'usb')
                    pi_ok, usb_ok = self.camera.capture(pi_path, usb_path, angle=current_angle)
                    
                    results = []
                    if pi_ok:
                        pi_captured += 1
                        size = os.path.getsize(pi_path) / 1024 if os.path.exists(pi_path) else 0
                        results.append(f"Pi:{size:.0f}KB")
                    if usb_ok:
                        usb_captured += 1
                        size = os.path.getsize(usb_path) / 1024 if os.path.exists(usb_path) else 0
                        results.append(f"USB:{size:.0f}KB")
                    print(f"    -> SAVED ({', '.join(results)})" if results else "    -> FAILED")
                else:
                    filepath = self.storage.get_filepath(current_angle)
                    success = self.camera.capture(filepath, angle=current_angle)
                    if success:
                        pi_captured += 1
                        size = os.path.getsize(filepath) / 1024 if os.path.exists(filepath) else 0
                        print(f"    -> SAVED ({size:.0f}KB)")
                    else:
                        print("    -> FAILED")
                
                progress_bar(i + 1, CONFIG.TOTAL_PHOTOS, "  Progress")
                
                # Rotate to next position
                if i < CONFIG.TOTAL_PHOTOS - 1:
                    self.motor.rotate_increment()
        
        except KeyboardInterrupt:
            print("\n\n  Scan aborted by user.")
        
        finally:
            self.camera.stop_video_recording()
            self.camera.stop_preview()
            self.motor.disable()
            self.motor.cleanup()
            self.camera.cleanup()
        
        # Summary
        print("\n" + "=" * 100)
        if use_dual:
            print(f"  SCAN COMPLETE: Pi={pi_captured}/{CONFIG.TOTAL_PHOTOS}, USB={usb_captured}/{CONFIG.TOTAL_PHOTOS}")
            log_main.info(f"Dual scan complete: Pi={pi_captured}, USB={usb_captured} for piece {piece_id}")
        else:
            print(f"  SCAN COMPLETE: {pi_captured}/{CONFIG.TOTAL_PHOTOS} images")
            log_main.info(f"Scan complete: {pi_captured}/{CONFIG.TOTAL_PHOTOS} images for piece {piece_id}")
        
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
        
        # Ask which camera to test
        print("\n  Select camera to test:")
        print("    [1] Pi Camera V3 (CSI)")
        print("    [2] USB Camera (Logitech BRIO)")
        print("    [3] Both cameras (dual preview)")
        print("    [0] Cancel")
        
        cam_choice = input("\n  Enter option: ").strip()
        
        if cam_choice == "0":
            return
        elif cam_choice == "1":
            self.camera = PiCameraController()
            cam_name = "Pi Camera"
        elif cam_choice == "2":
            # USB camera alone - preview enabled
            self.camera = USBCameraController(enable_preview=True)
            cam_name = "USB Camera"
        elif cam_choice == "3":
            # Dual mode - only Pi preview, USB runs in background
            self.camera = DualCameraManager()
            cam_name = "Dual Cameras (Pi preview only)"
        else:
            print("  Invalid option.")
            time.sleep(1)
            return
        
        if not self.camera.is_initialized:
            print(f"\n  {cam_name} not initialized. Check connection.")
            if hasattr(self.camera, 'cleanup'):
                self.camera.cleanup()
            input("\n  Press ENTER to continue...")
            return
        
        # Start preview window
        preview_ok = self.camera.start_preview()
        
        if preview_ok:
            print(f"\n  [PREVIEW] {cam_name} live video window opened")
            print("  [PREVIEW] Press 'Q' in preview window OR Ctrl+C here to stop")
        else:
            print("\n  [PREVIEW] Could not open preview window.")
        
        print("\n  Streaming live video...\n")
        
        try:
            frame = 0
            while True:
                # Check if preview thread stopped (user pressed Q)
                if hasattr(self.camera, 'preview_thread') and self.camera.preview_thread:
                    if not self.camera.preview_thread.is_alive():
                        print("\n\n  Preview window closed.")
                        break
                # For DualCameraManager, check both
                elif isinstance(self.camera, DualCameraManager):
                    pi_alive = self.camera.pi_camera and self.camera.pi_camera.preview_thread and self.camera.pi_camera.preview_thread.is_alive()
                    usb_alive = self.camera.usb_camera and self.camera.usb_camera.preview_thread and self.camera.usb_camera.preview_thread.is_alive()
                    if not pi_alive and not usb_alive:
                        print("\n\n  All preview windows closed.")
                        break
                
                frame += 1
                status = self.camera.get_status()
                print(f"\r  [LIVE] Frame {frame:05d} | {status}          ", end="", flush=True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        
        print("\n\n  Stopping preview...")
        if self.camera:
            self.camera.stop_preview()
            time.sleep(0.3)
            self.camera.cleanup()
            self.camera = None
        gc.collect()
        
        input("\n  Press ENTER to continue...")
    
    def camera_settings_menu(self):
        """Interactive camera settings adjustment with live preview."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                            CAMERA SETTINGS - LIVE ADJUSTMENT")
        print("=" * 100)
        
        if not CAMERA_AVAILABLE:
            print("\n  Pi Camera not available.")
            input("\n  Press ENTER to continue...")
            return
        
        print("\n  Initializing camera with live preview...")
        self.camera = PiCameraController()
        
        if not self.camera.is_initialized:
            print("  Camera initialization failed.")
            input("\n  Press ENTER to continue...")
            return
        
        # Create settings controller
        settings = CameraSettingsController(self.camera)
        
        # Start preview
        preview_ok = self.camera.start_preview()
        if not preview_ok:
            print("  Warning: Preview window could not be opened.")
        else:
            print("  [PREVIEW] Live preview opened - changes apply in real-time")
        
        while True:
            print("\n" + "-" * 80)
            print("  CURRENT SETTINGS:")
            print(f"    AF Mode: {settings.af_mode}")
            for key, ctrl in CameraSettingsController.CONTROLS.items():
                val = settings.get_control(key)
                print(f"    {ctrl['name']}: {val} {ctrl['unit']}")
            
            print("\n  COMMANDS:")
            print("    [1] Focus       [2] Exposure    [3] Gain")
            print("    [4] Brightness  [5] Contrast    [6] Saturation  [7] Sharpness")
            print("    [A] AF Mode (continuous/manual/auto)")
            print("    [R] Reset all to defaults")
            print("    [S] Toggle preview color swap (fix yellow->blue)")
            print("    [0] Exit settings")
            
            cmd = input("\n  Enter command: ").strip().lower()
            
            if cmd == "0":
                break
            elif cmd == "r":
                settings.reset_to_defaults()
                print("  Reset to defaults.")
            elif cmd == "s":
                CONFIG.PREVIEW_SWAP_RB = not CONFIG.PREVIEW_SWAP_RB
                print(f"  Preview color swap: {'ENABLED' if CONFIG.PREVIEW_SWAP_RB else 'DISABLED'}")
                print("  (Restart preview to see effect)")
            elif cmd == "a":
                print("\n  AF Modes: [1] Continuous  [2] Manual  [3] Auto (one-shot)")
                af_choice = input("  Select: ").strip()
                if af_choice == "1":
                    settings.set_af_mode('continuous')
                elif af_choice == "2":
                    settings.set_af_mode('manual')
                elif af_choice == "3":
                    settings.set_af_mode('auto')
            elif cmd in ["1", "2", "3", "4", "5", "6", "7"]:
                key_map = {"1": "focus", "2": "exposure", "3": "gain", 
                          "4": "brightness", "5": "contrast", "6": "saturation", "7": "sharpness"}
                key = key_map[cmd]
                ctrl = CameraSettingsController.CONTROLS[key]
                current = settings.get_control(key)
                
                print(f"\n  {ctrl['name']}: current={current}, range=[{ctrl['min']}, {ctrl['max']}], step={ctrl['step']}")
                print("  Enter new value, or +/- to adjust by step:")
                
                val_input = input(f"  [{key}] = ").strip()
                if val_input == "+":
                    settings.adjust_control(key, ctrl['step'])
                elif val_input == "-":
                    settings.adjust_control(key, -ctrl['step'])
                elif val_input:
                    try:
                        new_val = float(val_input)
                        settings.set_control(key, new_val)
                    except ValueError:
                        print("  Invalid value.")
        
        print("\n  Closing camera...")
        # Stop preview first, then cleanup
        self.camera.stop_preview()
        time.sleep(0.5)  # Allow Qt to process events
        self.camera.cleanup()
        self.camera = None
        gc.collect()
        print("  Camera closed.")
        input("\n  Press ENTER to continue...")
    
    def test_motor_menu(self):
        """Motor test and calibration menu."""
        while True:
            self.show_header()
            print("\n" + "=" * 100)
            print("                                MOTOR TEST & CALIBRATION")
            print("=" * 100)
            print(f"\n  Current: Increment={CONFIG.ROTATION_INCREMENT}deg | Calibration={CONFIG.CALIBRATION_FACTOR:.6f}")
            print(f"  Speed: Pulse={CONFIG.PULSE_DELAY_MS}ms | Step={CONFIG.STEP_DELAY_MS}ms")
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
        
        # Valid increments: divide 360 evenly and result in 4-72 photos (5-90 degrees)
        valid_increments = [i for i in range(5, 91) if 360 % i == 0]
        print(f"\n  Valid increments: {valid_increments}")
        
        try:
            new_val = input("\n  Enter new increment (degrees): ").strip()
            if new_val:
                new_increment = int(new_val)
                if new_increment in valid_increments:
                    CONFIG.ROTATION_INCREMENT = new_increment
                    CONFIG.TOTAL_PHOTOS = 360 // new_increment
                    log_main.info(f"Rotation increment changed to {new_increment}deg ({CONFIG.TOTAL_PHOTOS} photos)")
                    print(f"\n  Increment set to {new_increment} degrees")
                    print(f"  Total photos per scan: {CONFIG.TOTAL_PHOTOS}")
                elif 360 % new_increment == 0:
                    photos = 360 // new_increment
                    print(f"  Increment {new_increment} would result in {photos} photos.")
                    print(f"  Allowed range: 5-90 degrees (4-72 photos).")
                else:
                    print(f"  Increment {new_increment} does not divide 360 evenly.")
                    print(f"  Valid options: {valid_increments}")
        except ValueError:
            print("  Invalid input. Enter a number.")
        
        input("\n  Press ENTER to continue...")
    
    def modify_speed(self):
        """Modify motor speed settings."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                  MODIFY MOTOR SPEED")
        print("=" * 100)
        print(f"\n  Current pulse delay: {CONFIG.PULSE_DELAY_MS} ms")
        print(f"  Current step delay: {CONFIG.STEP_DELAY_MS} ms")
        print("\n  Lower delays = faster rotation")
        print("  Note: Python timing has ~1ms granularity; values < 0.5ms are unreliable")
        
        try:
            pulse_input = input(f"\n  Pulse delay in ms [0.5-10] ({CONFIG.PULSE_DELAY_MS}): ").strip()
            if pulse_input:
                pulse = float(pulse_input)
                CONFIG.PULSE_DELAY_MS = max(0.5, min(10, pulse))
                log_main.info(f"Pulse delay changed to {CONFIG.PULSE_DELAY_MS}ms")
                print(f"  Pulse delay set to {CONFIG.PULSE_DELAY_MS} ms")
            
            step_input = input(f"  Step delay in ms [1-50] ({CONFIG.STEP_DELAY_MS}): ").strip()
            if step_input:
                step = float(step_input)
                CONFIG.STEP_DELAY_MS = max(1, min(50, step))
                log_main.info(f"Step delay changed to {CONFIG.STEP_DELAY_MS}ms")
                print(f"  Step delay set to {CONFIG.STEP_DELAY_MS} ms")
        except ValueError:
            print("  Invalid input. Enter a number.")
        
        input("\n  Press ENTER to continue...")
    
    def motor_calibration(self):
        """Motor calibration menu."""
        self.show_header()
        print("\n" + "=" * 100)
        print("                                  MOTOR CALIBRATION")
        print("=" * 100)
        print(f"\n  Current calibration factor: {CONFIG.CALIBRATION_FACTOR:.6f}")
        print("\n  How calibration works:")
        print("    - If motor rotates LESS than commanded: INCREASE factor (e.g., 1.02)")
        print("    - If motor rotates MORE than commanded: DECREASE factor (e.g., 0.98)")
        print("    - Factor of 1.0 = no correction applied")
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
    log_main.info("="*60)
    log_main.info("Table Controle Carapace - Application Starting")
    log_main.info(f"GPIO available: {GPIO_AVAILABLE}, Camera available: {CAMERA_AVAILABLE}")
    log_main.info("="*60)
    try:
        app = Application()
        app.run()
        log_main.info("Application exited normally")
    except KeyboardInterrupt:
        log_main.info("Application terminated by user (Ctrl+C)")
        print("\n\n  Program terminated.")
        sys.exit(0)
    except Exception as e:
        log_main.exception(f"Fatal error: {e}")
        print(f"\n  Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
