"""Entry point for Table Controle Carapace."""

import sys
from .logging_setup import log_main
from .hardware import GPIO_AVAILABLE, CAMERA_AVAILABLE
from .application import Application


def main():
    log_main.info("=" * 60)
    log_main.info("Table Controle Carapace - Application Starting")
    log_main.info(f"GPIO available: {GPIO_AVAILABLE}, Camera available: {CAMERA_AVAILABLE}")
    log_main.info("=" * 60)
    try:
        app = Application()
        app.run()
        log_main.info("Application exited normally")
    except KeyboardInterrupt:
        log_main.info("Application terminated by user (Ctrl+C)")
        print("\n\n  Program terminated.")
        sys.exit(0)
    except Exception as e:
        log_main.exception(f"Fatal error: {e}")
        print(f"\n  Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
