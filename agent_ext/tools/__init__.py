"""Bounded local observations. No shell, target connection, cache or submission API."""

from .executor import ToolExecutor
from .inspection import Limits

__all__ = ["Limits", "ToolExecutor"]
