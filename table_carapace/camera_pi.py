"""Pi Camera Module V3 (IMX708) controller with live preview via OpenCV."""

import os
import gc
import time
import threading
from .config import CONFIG
from .logging_setup import log_camera
from .hardware import (
    cv2, CV2_AVAILABLE,
    Picamera2, Preview, controls, CAMERA_AVAILABLE,
    Image, PIL_AVAILABLE,
)


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
        self._cleanup_lock = threading.Lock()
        self._native_preview_started = False

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
            config = self.camera.create_still_configuration(
                main={"size": CONFIG.CAMERA_RESOLUTION, "format": "RGB888"},
                lores={"size": CONFIG.CAMERA_PREVIEW_SIZE, "format": "RGB888"},
                buffer_count=4,
                queue=True,
            )
            self.camera.configure(config)
            self.camera.set_controls({
                "AfMode": controls.AfModeEnum.Continuous,
                "AfSpeed": controls.AfSpeedEnum.Normal,
                "AwbEnable": True,
            })
            self.camera.start()
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

        if CV2_AVAILABLE:
            return self._start_opencv_preview()
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
            cv2.destroyWindow(self.PREVIEW_WINDOW)
            cv2.waitKey(1)
        except Exception as e:
            log_camera.debug(f"Stale preview window cleanup: {e}")

        try:
            cv2.namedWindow(self.PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.PREVIEW_WINDOW, 800, 600)
            cv2.waitKey(1)
        except Exception as e:
            print(f"  [CAMERA] Failed to create preview window: {e}")
            return

        frame_count = 0
        error_count = 0
        max_errors = 10

        while not self.stop_preview_flag:
            try:
                frame = self.camera.capture_array("lores")

                if frame is None:
                    error_count += 1
                    log_camera.warning(f"Frame capture returned None (error {error_count}/{max_errors})")
                    if error_count >= max_errors:
                        log_camera.error("Too many frame errors, stopping preview")
                        print(f"\n  [CAMERA] Too many frame errors, stopping preview")
                        break
                    continue

                if CONFIG.PREVIEW_SWAP_RB:
                    frame_bgr = frame
                else:
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                error_count = 0
                frame_count += 1

                if self.video_recording:
                    self.record_frame(frame_bgr)

                display_frame = self.add_angle_overlay(frame_bgr.copy(), self.current_angle, is_still=False)
                cv2.imshow(self.PREVIEW_WINDOW, display_frame)

                key = cv2.waitKey(16) & 0xFF
                if key == ord('q'):
                    break

            except Exception as e:
                error_count += 1
                if error_count >= max_errors:
                    print(f"\n  [CAMERA] Preview error: {e}")
                    break
                time.sleep(0.1)

        try:
            cv2.destroyWindow(self.PREVIEW_WINDOW)
            cv2.waitKey(1)
            cv2.destroyAllWindows()
            cv2.waitKey(1)
        except Exception as e:
            log_camera.debug(f"Pi preview window cleanup: {e}")

    def _start_native_preview(self):
        """Start preview using Picamera2 native preview."""
        preview_types = []
        if Preview is not None:
            preview_types = [
                ("DRM", getattr(Preview, "DRM", None)),
                ("QT", getattr(Preview, "QT", None)),
                ("QTGL", getattr(Preview, "QTGL", None)),
            ]

        for name, preview_type in preview_types:
            if preview_type is None:
                continue
            try:
                self.camera.start_preview(preview_type, x=100, y=100, width=800, height=600)
                self.preview_active = True
                self._native_preview_started = True
                return True
            except RuntimeError as e:
                if "event loop" in str(e).lower():
                    print(f"  [CAMERA] {name} preview skipped: event loop conflict")
                    if name in ("QT", "QTGL"):
                        continue
                continue
            except Exception as e:
                log_camera.debug(f"Native preview {name} failed: {e}")
                continue

        print("  [CAMERA] Preview window not available - running without preview")
        return False

    def stop_preview(self):
        """Stop live video preview."""
        self.stop_preview_flag = True

        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=2.0)

        # OpenCV window cleanup is handled by _opencv_preview_loop itself

        if self._native_preview_started and self.camera:
            try:
                self.camera.stop_preview()
            except Exception as e:
                log_camera.debug(f"Native preview stop: {e}")
            self._native_preview_started = False

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
            self.camera.set_controls({"AfTrigger": controls.AfTriggerEnum.Start})
            time.sleep(0.3)
            self.camera.capture_file(filepath, name="main")

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
                if angle is not None and CV2_AVAILABLE:
                    self._add_overlay_to_file(filepath, angle)
            else:
                with open(filepath, 'w') as f:
                    f.write("MOCK")
            return True
        except Exception as e:
            log_camera.debug(f"Mock capture failed: {e}")
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

        (text_w, text_h), baseline = cv2.getTextSize(text, self.OVERLAY_FONT, font_scale, thickness)

        padding = 20 if not is_still else 60
        x = frame.shape[1] - text_w - padding
        y = text_h + padding

        cv2.putText(frame, text, (x + 2, y + 2), self.OVERLAY_FONT, font_scale,
                    self.OVERLAY_SHADOW_COLOR, thickness + 2, cv2.LINE_AA)
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
            preferred = CONFIG.VIDEO_CODEC
            fallbacks = ['mp4v', 'avc1', 'XVID', 'MJPG']
            codecs = [preferred] + [c for c in fallbacks if c != preferred]

            fps = CONFIG.VIDEO_FPS
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
            h, w = frame.shape[:2]
            expected_w, expected_h = CONFIG.CAMERA_PREVIEW_SIZE
            if w != expected_w or h != expected_h:
                frame = cv2.resize(frame, (expected_w, expected_h))

            frame_with_overlay = self.add_angle_overlay(frame.copy(), self.current_angle, is_still=False)
            self.video_writer.write(frame_with_overlay)
            self.video_frame_count += 1
        except Exception as e:
            log_camera.debug(f"Frame recording error: {e}")

    def stop_video_recording(self):
        """Stop video recording and release writer."""
        was_recording = self.video_recording
        frame_count = getattr(self, 'video_frame_count', 0)
        self.video_recording = False
        if self.video_writer is not None:
            try:
                self.video_writer.release()
            except Exception as e:
                log_camera.debug(f"Video writer release: {e}")
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
        except Exception as e:
            log_camera.debug(f"Camera metadata query failed: {e}")
            return "Active"

    def cleanup(self):
        """Clean up camera resources."""
        with self._cleanup_lock:
            log_camera.info("Starting Pi camera cleanup")

            self.stop_video_recording()

            self.stop_preview_flag = True
            self.stop_preview()

            if self.preview_thread is not None:
                self.preview_thread.join(timeout=3.0)
                if self.preview_thread.is_alive():
                    log_camera.warning("Preview thread did not terminate cleanly")

            if self.camera:
                try:
                    self.camera.stop()
                    log_camera.debug("Camera stopped")
                except Exception as e:
                    log_camera.debug(f"Camera stop exception (may be expected): {e}")

                time.sleep(0.2)

                try:
                    self.camera.close()
                    log_camera.debug("Camera closed")
                except Exception as e:
                    log_camera.debug(f"Camera close exception (may be expected): {e}")
                self.camera = None

            self.is_initialized = False
            self.preview_active = False
            self.preview_thread = None
            self.stop_preview_flag = False
            self._native_preview_started = False
            self.video_writer = None
            self.video_recording = False
            self.video_frame_count = 0
            self.current_angle = 0

            gc.collect()
            time.sleep(0.3)
            gc.collect()
            time.sleep(1.0)
            log_camera.info("Pi camera cleanup complete")

    @staticmethod
    def is_camera_available():
        """Check if Pi camera hardware is available and not in use."""
        if not CAMERA_AVAILABLE:
            return False
        try:
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
