"""Windowless child-process settings for PHX2's Windows control plane.

The managed runtime starts console applications (PowerShell, taskkill and git)
from ``pythonw.exe``.  ``CREATE_NO_WINDOW`` is the authoritative isolation flag;
``STARTUPINFO``/``SW_HIDE`` is defense in depth for Windows versions and launch
contexts that still consult the child show-window setting.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Optional


def no_window_creation_flags() -> int:
    """Return ``CREATE_NO_WINDOW`` on Windows and zero elsewhere."""

    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def hidden_startupinfo() -> Optional[Any]:
    """Return a fresh ``STARTUPINFO`` requesting ``SW_HIDE`` on Windows."""

    if os.name != "nt":
        return None
    factory = getattr(subprocess, "STARTUPINFO", None)
    if factory is None:  # pragma: no cover - defensive for unusual runtimes
        return None
    startupinfo = factory()
    startupinfo.dwFlags |= int(
        getattr(subprocess, "STARTF_USESHOWWINDOW", 0))
    startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
    return startupinfo


__all__ = ("no_window_creation_flags", "hidden_startupinfo")
