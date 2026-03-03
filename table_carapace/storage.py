"""Storage manager for scan images and videos."""

import os
from datetime import datetime
from .config import CONFIG
from .logging_setup import log_storage


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
