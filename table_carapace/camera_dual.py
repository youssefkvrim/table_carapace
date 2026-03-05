"""Dual camera manager for simultaneous Pi Camera + USB camera operation."""

import gc
import time
import threading
from .config import CONFIG
from .logging_setup import log_camera
from .hardware import cv2, CV2_AVAILABLE, CAMERA_AVAILABLE
from .camera_pi import PiCameraController
from .camera_usb import USBCameraController


class DualCameraManager:
    """Manages both Pi Camera and USB camera simultaneously.

    Uses a COMBINED side-by-side preview window to show both cameras
    without Qt/threading conflicts.
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
            self.usb_camera = USBCameraController(camera_index=CONFIG.USB_CAMERA_INDEX, enable_preview=False)
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
            log_camera.warning("Cannot start preview: not initialized or no OpenCV")
            return False

        self.stop_preview_flag = False

        # Start USB camera background capture (no window)
        if self.usb_camera and self.usb_camera.is_initialized:
            log_camera.info("Starting USB camera background capture")
            self.usb_camera.start_preview()
            time.sleep(0.2)
        else:
            log_camera.warning("USB camera not available for preview")

        # Start combined preview thread
        log_camera.info("Starting combined preview thread")
        self.preview_thread = threading.Thread(target=self._combined_preview_loop, daemon=True)
        self.preview_thread.start()
        self.preview_active = True
        return True

    def _combined_preview_loop(self):
        """Combined preview showing both cameras side-by-side in ONE window.

        Pressing Q closes the preview window but does NOT stop video recording.
        The loop continues capturing frames for recording until stop_preview_flag is set.
        """
        preview_window_open = True
        try:
            cv2.namedWindow(self.PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.PREVIEW_WINDOW, 1280, 480)
        except Exception as e:
            log_camera.error(f"Failed to create combined preview window: {e}")
            preview_window_open = False

        preview_w, preview_h = CONFIG.USB_CAMERA_PREVIEW_SIZE

        while not self.stop_preview_flag:
            try:
                pi_frame = None
                usb_frame = None

                # Get Pi Camera frame
                if self.pi_camera and self.pi_camera.is_initialized and self.pi_camera.camera:
                    try:
                        frame = self.pi_camera.camera.capture_array("lores")
                        if frame is not None:
                            if CONFIG.PREVIEW_SWAP_RB:
                                pi_frame = frame
                            else:
                                pi_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                            pi_frame = cv2.resize(pi_frame, (preview_w, preview_h))

                            with self._frame_lock:
                                self._pi_frame = pi_frame.copy()

                            # Always record if recording is active
                            if self.video_recording and self.pi_video_writer:
                                self.pi_video_writer.write(pi_frame)
                    except Exception as e:
                        log_camera.debug(f"Pi frame capture error: {e}")

                # Get USB Camera frame
                if self.usb_camera and self.usb_camera.is_initialized:
                    try:
                        with self.usb_camera._frame_lock:
                            if self.usb_camera.last_frame is not None:
                                usb_frame = cv2.resize(self.usb_camera.last_frame.copy(), (preview_w, preview_h))

                                with self._frame_lock:
                                    self._usb_frame = usb_frame.copy()

                                # Always record if recording is active
                                if self.video_recording and self.usb_video_writer:
                                    self.usb_video_writer.write(usb_frame)
                    except Exception as e:
                        log_camera.debug(f"Error getting USB frame: {e}")

                # Only display if preview window is still open
                if preview_window_open:
                    # Create combined frame
                    if pi_frame is not None and usb_frame is not None:
                        combined = cv2.hconcat([pi_frame, usb_frame])
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
                        time.sleep(0.05)
                        continue

                    # Add angle overlay
                    angle_text = f"Angle: {int(self.current_angle):03d} deg"
                    cv2.putText(combined, angle_text, (combined.shape[1] - 200, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

                    cv2.imshow(self.PREVIEW_WINDOW, combined)

                    if cv2.waitKey(16) & 0xFF == ord('q'):
                        # Close preview window but keep loop running for recording
                        try:
                            cv2.destroyWindow(self.PREVIEW_WINDOW)
                            for _ in range(5):
                                cv2.waitKey(1)
                            cv2.destroyAllWindows()
                            for _ in range(5):
                                cv2.waitKey(1)
                        except Exception:
                            pass
                        preview_window_open = False
                        if self.video_recording:
                            print("\n  [PREVIEW] Window closed — video recording continues")
                        else:
                            break  # No recording active, exit the loop
                else:
                    # No preview window — just pace the loop for recording
                    if not self.video_recording:
                        break  # Nothing left to do
                    if pi_frame is None and usb_frame is None:
                        time.sleep(0.05)
                    else:
                        time.sleep(0.033)  # ~30 fps capture rate

            except Exception as e:
                log_camera.error(f"Combined preview error: {e}")
                time.sleep(0.1)

        if preview_window_open:
            try:
                cv2.destroyWindow(self.PREVIEW_WINDOW)
                for _ in range(5):
                    cv2.waitKey(1)
                cv2.destroyAllWindows()
                for _ in range(5):
                    cv2.waitKey(1)
            except Exception as e:
                log_camera.debug(f"Combined preview window cleanup: {e}")

        log_camera.info("Combined preview loop ended")

    def stop_preview(self):
        """Stop combined preview."""
        self.stop_preview_flag = True

        if self.usb_camera:
            self.usb_camera.stop_preview()

        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=2.0)

        self.preview_active = False
        self.preview_thread = None

    def capture(self, pi_filepath, usb_filepath=None, angle=None):
        """Capture from both cameras. Returns: (pi_success, usb_success)"""
        pi_ok = False
        usb_ok = False

        if self.pi_camera and pi_filepath:
            pi_ok = self.pi_camera.capture(pi_filepath, angle)

        if self.usb_camera and usb_filepath:
            usb_ok = self.usb_camera.capture(usb_filepath, angle)

        return pi_ok, usb_ok

    def _create_video_writer(self, filepath, frame_size):
        """Create a VideoWriter with codec fallback chain."""
        preferred = CONFIG.VIDEO_CODEC
        fallbacks = ['mp4v', 'avc1', 'XVID', 'MJPG']
        codecs = [preferred] + [c for c in fallbacks if c != preferred]
        fps = CONFIG.VIDEO_FPS

        for codec in codecs:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(filepath, fourcc, fps, frame_size)
            if writer.isOpened():
                log_camera.info(f"Video started: {filepath} (codec={codec}, {frame_size[0]}x{frame_size[1]}@{fps}fps)")
                return writer
            writer.release()
            log_camera.debug(f"Codec {codec} failed for {filepath}, trying next")

        log_camera.error(f"No compatible video codec found for {filepath}")
        return None

    def start_video_recording(self, pi_filepath, usb_filepath=None):
        """Start video recording on both cameras at combined preview resolution."""
        pi_ok = False
        usb_ok = False

        pi_size = CONFIG.USB_CAMERA_PREVIEW_SIZE
        usb_size = CONFIG.USB_CAMERA_PREVIEW_SIZE

        if pi_filepath:
            try:
                self.pi_video_writer = self._create_video_writer(pi_filepath, pi_size)
                pi_ok = self.pi_video_writer is not None
            except Exception as e:
                log_camera.error(f"Failed to start Pi video: {e}")

        if usb_filepath:
            try:
                self.usb_video_writer = self._create_video_writer(usb_filepath, usb_size)
                usb_ok = self.usb_video_writer is not None
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
            except Exception as e:
                log_camera.debug(f"Pi video writer release: {e}")
            self.pi_video_writer = None

        if self.usb_video_writer:
            try:
                self.usb_video_writer.release()
            except Exception as e:
                log_camera.debug(f"USB video writer release: {e}")
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

            self.stop_video_recording()

            self.stop_preview_flag = True
            self.stop_preview()

            if self.preview_thread and self.preview_thread.is_alive():
                self.preview_thread.join(timeout=3.0)
            self.preview_thread = None

            if self.usb_camera:
                log_camera.debug("Cleaning up USB camera")
                self.usb_camera.cleanup()
                self.usb_camera = None

            if self.pi_camera:
                log_camera.debug("Cleaning up Pi camera")
                self.pi_camera.cleanup()
                self.pi_camera = None

            with self._frame_lock:
                self._pi_frame = None
                self._usb_frame = None

            self.is_initialized = False
            self.preview_active = False

            gc.collect()
            time.sleep(0.5)
            gc.collect()
            time.sleep(1.0)
            log_camera.info("DualCameraManager cleanup complete")
