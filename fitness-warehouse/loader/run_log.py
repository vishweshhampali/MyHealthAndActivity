"""Configure a per-run logger: writes to both console and a timestamped file."""
import logging
import os
from datetime import datetime


def setup(logs_dir: str) -> logging.Logger:
    """Create logs_dir if needed and return a logger writing to console + run_<timestamp>.log."""
    os.makedirs(logs_dir, exist_ok=True)
    filename = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    path = os.path.join(logs_dir, filename)

    logger = logging.getLogger("fitness_loader")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(message)s")

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
