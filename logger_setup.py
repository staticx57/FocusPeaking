"""
Logging configuration for FLIR Boson Focus Peaking.

Provides centralized logging setup with file and console output,
rotation, and configurable log levels.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

from config import (
    LOG_FILE,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
    ENABLE_CONSOLE_LOGGING,
    get_log_path,
)


def setup_logging(
    log_file: Optional[str] = None,
    log_level: Optional[str] = None,
    console: bool = None
) -> logging.Logger:
    """
    Setup application logging with file and optional console output.

    Args:
        log_file: Path to log file (default from config)
        log_level: Logging level (default from config)
        console: Enable console logging (default from config)

    Returns:
        Configured logger instance
    """
    # Use defaults from config if not specified
    if log_file is None:
        log_file = str(get_log_path())

    if log_level is None:
        log_level = LOG_LEVEL

    if console is None:
        console = ENABLE_CONSOLE_LOGGING

    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT)

    # File handler with rotation
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info("=" * 60)
        logger.info("FLIR Boson Focus Peaking - Logging initialized")
        logger.info(f"Log level: {log_level}")
        logger.info(f"Log file: {log_file}")
        logger.info("=" * 60)

    except Exception as e:
        print(f"Warning: Could not create log file handler: {e}")

    # Console handler (optional)
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)

        # Use simpler format for console
        console_formatter = logging.Formatter(
            '%(levelname)s - %(name)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin class to add logging capability to any class.

    Usage:
        class MyClass(LoggerMixin):
            def __init__(self):
                super().__init__()
                self.logger.info("MyClass initialized")
    """

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        return logging.getLogger(self.__class__.__name__)
