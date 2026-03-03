"""NEMA 23 stepper motor controller via DM556 driver (gpiozero / Pi 5 compatible)."""

import time
from .config import CONFIG
from .logging_setup import log_motor
from .hardware import OutputDevice


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
