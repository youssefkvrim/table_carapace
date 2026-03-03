"""Logging configuration for Table Controle Carapace."""

import os
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
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
