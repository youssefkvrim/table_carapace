"""USB camera controller (Logitech BRIO / UVC cameras) via OpenCV."""

import os
import gc
import time
import threading
from .config import CONFIG
from .logging_setup import log_camera
from .hardware import cv2, CV2_AVAILABLE


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
        """Find USB camera by querying v4l2 for UVC devices only."""
        import subprocess

        # Try the configured index first (fast path)
        if self.camera_index is not None:
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
            if cap.isOpened():
                # Set short timeout for test read
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ret, _ = cap.read()
                cap.release()
                if ret:
                    log_camera.info(f"Using configured USB camera index: {self.camera_index}")
                    return self.camera_index

        # Use v4l2-ctl to find ONLY video capture devices (not media controllers)
        usb_video_indices = []
        try:
            result = subprocess.run(['v4l2-ctl', '--list-devices'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                current_device = None
                for line in lines:
                    if line and not line.startswith('\t') and not line.startswith(' '):
                        current_device = line.strip()
                    elif line.strip().startswith('/dev/video'):
                        dev = line.strip()
                        # Only consider USB/UVC devices, skip Pi camera (rp1)
                        if current_device and 'rp1' not in current_device.lower():
                            try:
                                idx = int(dev.replace('/dev/video', ''))
                                # Only add the FIRST video device per camera (captures video)
                                # Subsequent ones are usually metadata/control interfaces
                                if not usb_video_indices or usb_video_indices[-1][0] != idx - 1:
                                    usb_video_indices.append((idx, current_device))
                                    log_camera.info(f"Found USB video device: {current_device} -> /dev/video{idx}")
                            except ValueError:
                                pass
        except Exception as e:
            log_camera.debug(f"v4l2-ctl failed: {e}")

        # Try found USB devices (should be quick - only real video devices)
        for idx, name in usb_video_indices:
            log_camera.info(f"Trying USB camera at index {idx}")
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    log_camera.info(f"USB camera ready: {name} at index {idx}")
                    return idx
                else:
                    log_camera.debug(f"Index {idx} opened but couldn't read frame")

        # Quick fallback: try common USB camera indices (8, 10 are typical for BRIO)
        # Skip indices that are known to timeout (20+)
        for idx in [8, 10, 2, 4]:
            log_camera.debug(f"Quick scan index {idx}")
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    log_camera.info(f"USB camera found at index {idx}")
                    return idx

        log_camera.warning("No USB camera found")
        return None

    def _initialize(self):
        """Initialize USB camera using V4L2 backend."""
        try:
            # Find the camera
            idx = self._find_usb_camera()
            if idx is None:
                log_camera.warning("No USB camera found")
                print("  [USB CAM] Not found - check connection")
                return

            self.camera_index = idx
            log_camera.info(f"Initializing USB camera at index {idx} with V4L2 backend")

            # Use V4L2 backend explicitly to avoid GStreamer issues
            self.camera = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if not self.camera.isOpened():
                log_camera.error(f"Failed to open USB camera at index {idx}")
                self.camera = None
                print(f"  [USB CAM] Failed to open at index {idx}")
                return

            # Set MJPG format for better performance with USB cameras
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            # Set resolution
            w, h = CONFIG.USB_CAMERA_RESOLUTION
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

            # Set buffer size to 1 to get latest frame
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Get actual resolution
            actual_w = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Verify we can actually read frames
            ret, frame = self.camera.read()
            if not ret or frame is None:
                log_camera.error(f"USB camera at index {idx} cannot read frames")
                self.camera.release()
                self.camera = None
                print(f"  [USB CAM] Cannot read frames from index {idx}")
                return

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
        log_camera.info("USB camera capture loop started")
        frame_count = 0
        error_count = 0
        max_errors = 30

        while not self._stop_capture_flag:
            try:
                if self.camera is None or not self.camera.isOpened():
                    log_camera.error("USB camera not available in capture loop")
                    break

                ret, frame = self.camera.read()
                if not ret or frame is None:
                    error_count += 1
                    if error_count >= max_errors:
                        log_camera.error(f"USB camera: too many read errors ({error_count})")
                        break
                    time.sleep(0.05)
                    continue

                error_count = 0  # Reset on success
                frame_count += 1

                with self._frame_lock:
                    self.last_frame = frame.copy()

                # Record if active
                if self.video_recording and self.video_writer:
                    self.video_writer.write(frame)
                    self.video_frame_count += 1

                # Log periodically
                if frame_count % 100 == 0:
                    log_camera.debug(f"USB camera: captured {frame_count} frames")

                time.sleep(0.033)  # ~30fps capture rate

            except Exception as e:
                log_camera.error(f"USB capture error: {e}")
                error_count += 1
                if error_count >= max_errors:
                    break
                time.sleep(0.1)

        log_camera.info(f"USB camera capture loop ended after {frame_count} frames")

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
        except Exception as e:
            log_camera.debug(f"USB preview window cleanup: {e}")

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
        """Start video recording at preview resolution with codec fallback."""
        if not self.is_initialized:
            return False
        try:
            preferred = CONFIG.VIDEO_CODEC
            fallbacks = ['mp4v', 'avc1', 'XVID', 'MJPG']
            codecs = [preferred] + [c for c in fallbacks if c != preferred]
            fps = CONFIG.VIDEO_FPS
            frame_size = CONFIG.USB_CAMERA_PREVIEW_SIZE

            for codec in codecs:
                fourcc = cv2.VideoWriter_fourcc(*codec)
                self.video_writer = cv2.VideoWriter(filepath, fourcc, fps, frame_size)
                if self.video_writer.isOpened():
                    self.video_recording = True
                    self.video_frame_count = 0
                    log_camera.info(f"USB video recording started: {filepath} (codec={codec}, {frame_size[0]}x{frame_size[1]}@{fps}fps)")
                    return True
                self.video_writer.release()
                log_camera.debug(f"USB video codec {codec} failed, trying next")

            log_camera.error("No compatible video codec found for USB camera")
            self.video_writer = None
            return False
        except Exception as e:
            log_camera.error(f"USB video recording start failed: {e}")
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
                except Exception as e:
                    log_camera.debug(f"USB camera release: {e}")
                self.camera = None

            self.is_initialized = False
            with self._frame_lock:
                self.last_frame = None

            gc.collect()
            time.sleep(0.2)
            log_camera.info("USB camera cleanup complete")
