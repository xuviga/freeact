"""File-based logging for freeact. Writes to ~/.freeact/freeact.log.

Usage:
    from freeact.logger import log
    log("Starting browser...")
    log("Error connecting", level="error")
"""

import time

from freeact.config import FREACT_HOME

LOG_FILE = FREACT_HOME / "freeact.log"


def log(message: str, level: str = "info") -> None:
    """Append a timestamped message to the log file."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level.upper()}] {message}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def log_error(message: str) -> None:
    log(message, level="error")


def log_warn(message: str) -> None:
    log(message, level="warn")


def log_debug(message: str) -> None:
    log(message, level="debug")
