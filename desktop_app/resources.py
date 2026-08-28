"""Resource resolution that works from source trees and PyInstaller bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource from ``_MEIPASS`` or the source root."""
    roots = (
        [
            Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)),
            Path(sys.executable).parent,
        ]
        if getattr(sys, "frozen", False)
        else [Path(__file__).resolve().parents[1]]
    )
    for root in roots:
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return candidate
    return roots[0].joinpath(*parts)
