"""
Abstract base service.

All concrete services inherit from this class to share
the data-directory dependency and the logger instance.
"""

from __future__ import annotations

import logging
from abc import ABC


class BaseService(ABC):
    """
    Common ancestor for all service classes.

    Attributes:
        data_dir: Path to the CSV data directory.
        log:      Module-scoped logger for the concrete subclass.
    """

    def __init__(self, data_dir: str) -> None:
        """
        Args:
            data_dir: Absolute path to the directory containing CSV files.
        """
        self._data_dir: str           = data_dir
        self.log:       logging.Logger = logging.getLogger(
            type(self).__module__ + "." + type(self).__name__
        )
