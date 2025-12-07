from __future__ import annotations

import logging
import os
from pathlib import Path

from .paths import Paths


def setup_logging(paths: Paths, level: str | int = "INFO") -> None:
    log_level = logging.getLevelName(level) if isinstance(level, str) else level
    logs_dir = paths.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "knowever.log"

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    # Quiet down noisy libraries
    for noisy in ["urllib3", "botocore"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def env_log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO")
