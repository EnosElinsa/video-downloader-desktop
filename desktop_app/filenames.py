"""Filename helpers shared by downloads and batch workflows."""

from __future__ import annotations

import re


def sanitize_filename(filename: str) -> str:
    """Replace characters Windows does not permit in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "_", filename)
