"""Camera settings controller for real-time Pi Camera V3 adjustments."""

import time
from .logging_setup import log_camera
from .hardware import controls, CAMERA_AVAILABLE


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
        value = max(ctrl['min'], min(ctrl['max'], value))

        try:
            if key == 'focus':
                self.pi_camera.camera.set_controls({
                    "AfMode": controls.AfModeEnum.Manual,
                    "LensPosition": value,
                })
                self.af_mode = 'manual'
                self.current_values[key] = value
                time.sleep(0.5)
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
