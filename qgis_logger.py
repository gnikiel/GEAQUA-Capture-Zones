"""
QGIS logging handler for GEAQUA Capture Zones

This module provides a custom logging handler that integrates Python's
standard logging with QGIS's message log system, making logs visible
in the QGIS Log Messages Panel.
"""

import logging
from qgis.core import QgsMessageLog
from .qt_compat import (
    QGIS_MESSAGE_INFO, QGIS_MESSAGE_WARNING, QGIS_MESSAGE_CRITICAL,
)


class QgsLogHandler(logging.Handler):
    """
    Custom logging handler that writes to QGIS message log.

    This handler translates Python logging levels to QGIS message levels
    and makes logs visible in the QGIS Log Messages Panel (View -> Panels -> Log Messages).
    """

    # Map Python logging levels to QGIS message levels
    LEVEL_MAP = {
        logging.DEBUG: QGIS_MESSAGE_INFO,
        logging.INFO: QGIS_MESSAGE_INFO,
        logging.WARNING: QGIS_MESSAGE_WARNING,
        logging.ERROR: QGIS_MESSAGE_CRITICAL,
        logging.CRITICAL: QGIS_MESSAGE_CRITICAL,
    }

    def __init__(self, tag='GEAQUA Capture Zones'):
        """
        Initialize the QGIS log handler.

        Args:
            tag (str): The tag/category name that will appear in QGIS log panel
        """
        super().__init__()
        self.tag = tag

    def emit(self, record):
        """
        Emit a log record to QGIS message log.

        Args:
            record: The LogRecord to be logged
        """
        try:
            # Format the message
            msg = self.format(record)

            # Get the appropriate QGIS message level
            qgis_level = self.LEVEL_MAP.get(record.levelno, QGIS_MESSAGE_INFO)

            # Write to QGIS message log
            QgsMessageLog.logMessage(msg, self.tag, qgis_level)

        except Exception:
            self.handleError(record)


def setup_qgis_logger(name, level=logging.INFO, tag='GEAQUA Capture Zones'):
    """
    Set up a logger that writes to both console and QGIS message log.

    Args:
        name (str): Logger name (typically __name__)
        level (int): Logging level (e.g., logging.INFO, logging.DEBUG)
        tag (str): Tag/category for QGIS log panel

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False  # Don't propagate to root logger

    # Create QGIS handler
    qgis_handler = QgsLogHandler(tag)
    qgis_handler.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    qgis_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(qgis_handler)

    # Optionally also add console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name):
    """
    Get or create a logger configured for QGIS.

    This is a convenience function that ensures consistent logging setup.

    Args:
        name (str): Logger name (typically __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    return setup_qgis_logger(name)
