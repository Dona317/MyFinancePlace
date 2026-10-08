"""Entry point of the packaged app (PyInstaller cannot start `python -m desktop.main`)."""
import multiprocessing
import sys

from desktop.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
