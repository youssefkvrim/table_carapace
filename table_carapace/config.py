"""Configuration and settings persistence for Table Controle Carapace."""

import os
import json
from .logging_setup import log_main


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
    STEP_DELAY_MS = 10        # delay between steps
    CALIBRATION_FACTOR = 1.046648

    # VIDEO SETTINGS
    VIDEO_CODEC = "mp4v"      # Options: "mp4v" (compatible), "avc1" (H.264, smaller), "XVID", "MJPG"
    VIDEO_FPS = 15            # Frames per second for scan video

    # PI CAMERA SETTINGS (CSI - Camera Module V3)
    CAMERA_RESOLUTION = (4608, 2592)
    CAMERA_PREVIEW_SIZE = (800, 600)
    CAMERA_QUALITY = 95
    CAPTURE_DELAY = 0.5
    # Set to True if preview colors are wrong (swap R and B channels)
    PREVIEW_SWAP_RB = True

    # USB CAMERA SETTINGS (Logitech BRIO or similar)
    USB_CAMERA_ENABLED = True
    USB_CAMERA_INDEX = 0      # Will auto-detect if this fails
    USB_CAMERA_RESOLUTION = (1920, 1080)
    USB_CAMERA_PREVIEW_SIZE = (640, 480)

    # DUAL CAMERA MODE
    DUAL_CAMERA_ENABLED = True  # Capture from both cameras simultaneously

    # STORAGE SETTINGS
    LOCAL_STORAGE_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "table_carapace", "scans")
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

# File paths for persistence
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CALIBRATION_FILE = os.path.join(_BASE_DIR, "calibration.json")
SETTINGS_FILE = os.path.join(_BASE_DIR, "settings.json")

# Persistable settings keys and their Config attribute names
_PERSISTABLE_SETTINGS = {
    'calibration_factor': 'CALIBRATION_FACTOR',
    'rotation_increment': 'ROTATION_INCREMENT',
    'pulse_delay_ms': 'PULSE_DELAY_MS',
    'step_delay_ms': 'STEP_DELAY_MS',
    'preview_swap_rb': 'PREVIEW_SWAP_RB',
}


def load_settings():
    """Load all persisted settings from settings.json (with calibration.json fallback)."""
    # Try new unified settings file first
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                data = json.load(f)
            for json_key, attr_name in _PERSISTABLE_SETTINGS.items():
                if json_key in data:
                    setattr(CONFIG, attr_name, data[json_key])
            # Keep TOTAL_PHOTOS in sync with ROTATION_INCREMENT
            if 360 % CONFIG.ROTATION_INCREMENT == 0:
                CONFIG.TOTAL_PHOTOS = 360 // CONFIG.ROTATION_INCREMENT
            log_main.info(f"Settings loaded from {SETTINGS_FILE}")
            return True
    except Exception as e:
        log_main.warning(f"Failed to load settings: {e}")

    # Fallback: legacy calibration.json (migrate on next save)
    try:
        if os.path.exists(CALIBRATION_FILE):
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                CONFIG.CALIBRATION_FACTOR = data.get('calibration_factor', 1.046648)
                log_main.info("Loaded legacy calibration.json")
                return True
    except Exception as e:
        log_main.warning(f"Failed to load legacy calibration: {e}")
    return False


def save_settings():
    """Save all persistable settings to settings.json."""
    data = {}
    for json_key, attr_name in _PERSISTABLE_SETTINGS.items():
        data[json_key] = getattr(CONFIG, attr_name)
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        log_main.info(f"Settings saved to {SETTINGS_FILE}")
        return True
    except Exception as e:
        log_main.error(f"Failed to save settings: {e}")
        return False


# Backward-compatible wrappers
def load_calibration():
    load_settings()
    return CONFIG.CALIBRATION_FACTOR


def save_calibration(factor):
    CONFIG.CALIBRATION_FACTOR = factor
    return save_settings()
