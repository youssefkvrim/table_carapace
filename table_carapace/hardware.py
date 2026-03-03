"""Hardware imports with graceful fallbacks for non-Pi systems."""

from .logging_setup import log_main

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
    Picamera2 = None
    Preview = None
    controls = None

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
