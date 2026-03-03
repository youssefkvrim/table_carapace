"""Main application class with TUI menus."""

import os
import sys
import gc
import time
import shutil

from .config import CONFIG, load_calibration, save_calibration, save_settings
from .logging_setup import log_main, log_camera
from .hardware import CAMERA_AVAILABLE, CV2_AVAILABLE
from .ui import clear_screen, progress_bar, PROJECT_TITLE, LICENSE_TEXT
from .motor import MotorController
from .camera_pi import PiCameraController
from .camera_usb import USBCameraController
from .camera_dual import DualCameraManager
from .camera_settings import CameraSettingsController
from .storage import StorageManager


class Application:
    def __init__(self):
        self.motor = None
        self.camera = None
        self.storage = None
        self._capture_camera = None  # Persistent camera for captures (avoids re-init)
        load_calibration()

    def show_header(self):
        """Display the persistent header with project title and license."""
        clear_screen()
        print(PROJECT_TITLE)
        print(LICENSE_TEXT)

    def show_main_menu(self):
        """Display main menu options."""
        self.show_header()

        print("\n" + "=" * 100)
        print("                                      MAIN MENU")
        print("=" * 100)
        print(f"\n  Current Settings: Increment={CONFIG.ROTATION_INCREMENT}deg | Photos={CONFIG.TOTAL_PHOTOS} | Calibration={CONFIG.CALIBRATION_FACTOR:.4f}")
        print(f"  Storage: {CONFIG.LOCAL_STORAGE_PATH}")

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
        try:
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
        finally:
            if self._capture_camera is not None:
                self._capture_camera.cleanup()
                self._capture_camera = None

    def _get_capture_camera(self, use_dual):
        """Get or create the persistent capture camera."""
        if self._capture_camera is not None:
            if self._capture_camera.is_initialized:
                is_dual = isinstance(self._capture_camera, DualCameraManager)
                if is_dual == use_dual:
                    return self._capture_camera
            log_camera.info("Cleaning up stale capture camera for re-creation")
            self._capture_camera.cleanup()
            self._capture_camera = None
            gc.collect()
            time.sleep(0.5)

        if use_dual:
            self._capture_camera = DualCameraManager()
        else:
            self._capture_camera = PiCameraController()
        return self._capture_camera

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
            if piece_number < 0 or piece_number > 999999:
                print("  Piece number must be between 0 and 999999.")
                time.sleep(1)
                return
        except ValueError:
            print("  Invalid number.")
            time.sleep(1)
            return

        use_dual = CONFIG.DUAL_CAMERA_ENABLED and CONFIG.USB_CAMERA_ENABLED

        # Confirmation before scan
        piece_id_preview = CONFIG.PIECE_ID_FORMAT.format(piece_number)
        cam_mode = "Dual (Pi + USB)" if use_dual else "Pi Camera"
        print(f"\n  Summary:")
        print(f"    Piece:     {piece_id_preview}")
        print(f"    Photos:    {CONFIG.TOTAL_PHOTOS} at {CONFIG.ROTATION_INCREMENT} deg increments")
        print(f"    Camera:    {cam_mode}")
        print(f"    Calibr.:   {CONFIG.CALIBRATION_FACTOR:.6f}")

        # Check disk space
        try:
            disk = shutil.disk_usage(CONFIG.LOCAL_STORAGE_PATH)
            free_mb = disk.free / (1024 * 1024)
            required_mb = CONFIG.TOTAL_PHOTOS * 10 * (2 if use_dual else 1)
            print(f"    Disk free: {free_mb:.0f} MB (need ~{required_mb} MB)")
            if free_mb < required_mb:
                print(f"\n  WARNING: Low disk space! Only {free_mb:.0f} MB free, need ~{required_mb} MB.")
                print("  Scan may fail to save images.")
                abort = input("  Continue anyway? [y/N]: ").strip().lower()
                if abort != 'y':
                    print("  Scan cancelled.")
                    return
        except Exception as e:
            log_main.warning(f"Could not check disk space: {e}")

        print("\n  Initializing hardware...")
        progress_bar(0, 4, "  Init")

        self.motor = MotorController()
        progress_bar(1, 4, "  Init")

        self.camera = self._get_capture_camera(use_dual)
        if use_dual:
            print("\n  [DUAL CAM] Dual camera mode enabled")
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

                self.camera.set_current_angle(current_angle)

                status = self.camera.get_status()
                print(f"  [{i+1:2d}/{CONFIG.TOTAL_PHOTOS}] Angle: {current_angle:03d}deg | {status}")

                time.sleep(CONFIG.CAPTURE_DELAY)

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

                if i < CONFIG.TOTAL_PHOTOS - 1:
                    self.motor.rotate_increment()

        except KeyboardInterrupt:
            print("\n\n  Scan aborted by user.")

        finally:
            self.camera.stop_video_recording()
            self.camera.stop_preview()
            self.motor.disable()
            self.motor.cleanup()

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
            self.camera = USBCameraController(enable_preview=True)
            cam_name = "USB Camera"
        elif cam_choice == "3":
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
                if hasattr(self.camera, 'preview_thread') and self.camera.preview_thread:
                    if not self.camera.preview_thread.is_alive():
                        print("\n\n  Preview window closed.")
                        break
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

        settings = CameraSettingsController(self.camera)

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
                save_settings()
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
        self.camera.stop_preview()
        time.sleep(0.5)
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

        valid_increments = [i for i in range(5, 91) if 360 % i == 0]
        print(f"\n  Valid increments: {valid_increments}")

        try:
            new_val = input("\n  Enter new increment (degrees): ").strip()
            if new_val:
                new_increment = int(new_val)
                if new_increment in valid_increments:
                    CONFIG.ROTATION_INCREMENT = new_increment
                    CONFIG.TOTAL_PHOTOS = 360 // new_increment
                    save_settings()
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

            save_settings()
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
    5. Images saved to: ~/Desktop/table_carapace/scans/

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
