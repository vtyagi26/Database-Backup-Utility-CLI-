import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# Custom rich theme
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "bold magenta",
})

console = Console(theme=custom_theme)
error_console = Console(stderr=True, theme=custom_theme)


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON objects for machine-parsable log files."""
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "backup_id"):
            log_entry["backup_id"] = record.backup_id
        if hasattr(record, "duration"):
            log_entry["duration_seconds"] = record.duration
        if hasattr(record, "status"):
            log_entry["status"] = record.status
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logger(
    log_file: Optional[str] = "backups/backup_activity.log",
    verbose: bool = False,
    json_logging: bool = False,
) -> logging.Logger:
    """Configures the root/backup utility logger with Rich and File handlers."""
    logger = logging.getLogger("backup_util")
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    # Avoid duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger

    # Rich Console Handler
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    rich_handler.setLevel(level)
    logger.addHandler(rich_handler)

    # File Handler
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)  # Always log debug to file

            if json_logging or log_file.endswith(".json"):
                file_handler.setFormatter(JsonFormatter())
            else:
                formatter = logging.Formatter(
                    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                file_handler.setFormatter(formatter)

            logger.addHandler(file_handler)
        except Exception as e:
            console.print(f"[warning]Warning: Could not open log file '{log_file}': {e}[/warning]")

    return logger


def get_logger() -> logging.Logger:
    """Returns the backup utility logger."""
    logger = logging.getLogger("backup_util")
    if not logger.handlers:
        return setup_logger()
    return logger
