"""Pure release-build validation helpers shared by tests and PowerShell."""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path


SUPPORTED_PYTHON_MINORS = {11, 12, 13}
PINNED_PYINSTALLER = "6.14.2"


def validate_release_environment(
    *,
    platform_name: str | None = None,
    machine: str | None = None,
    pointer_bits: int | None = None,
    python_version: tuple[int, int] | None = None,
    pyinstaller_version: str | None = None,
) -> None:
    """Reject environments that cannot truthfully produce a Windows x64 build."""
    platform_name = sys.platform if platform_name is None else platform_name
    machine = __import__("platform").machine() if machine is None else machine
    pointer_bits = struct.calcsize("P") * 8 if pointer_bits is None else pointer_bits
    python_version = (sys.version_info.major, sys.version_info.minor) if python_version is None else python_version
    if platform_name != "win32":
        raise RuntimeError("Windows x64 packaging requires sys.platform == 'win32'.")
    if machine.upper() not in {"AMD64", "X86_64"}:
        raise RuntimeError(f"Windows x64 packaging requires AMD64/x86_64, got {machine!r}.")
    if pointer_bits != 64:
        raise RuntimeError(f"Windows x64 packaging requires a 64-bit Python, got {pointer_bits}-bit.")
    if python_version[0] != 3 or python_version[1] not in SUPPORTED_PYTHON_MINORS:
        raise RuntimeError("Release packaging requires the pinned Python 3.11-3.13 toolchain.")
    if pyinstaller_version is not None and pyinstaller_version != PINNED_PYINSTALLER:
        raise RuntimeError(
            f"Release packaging requires PyInstaller {PINNED_PYINSTALLER}, got {pyinstaller_version}."
        )


def parse_sha256_manifest(text: str) -> dict[str, str]:
    """Parse and validate the two-space SHA-256 manifest format."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([^\\/\r\n]+)", line)
        if not match:
            raise ValueError(f"Invalid SHA256SUMS line: {line!r}")
        digest, filename = match.groups()
        if filename in result:
            raise ValueError(f"Duplicate checksum entry: {filename}")
        result[filename] = digest.lower()
    required = {"VideoDownloader-windows-x64.zip", "VideoDownloader-windows-x64.exe"}
    if set(result) != required:
        raise ValueError(f"Checksum manifest must cover exactly {sorted(required)}")
    return result


def find_optional_ffmpeg_document(executable: str | Path, names=("LICENSE", "README.txt")) -> Path | None:
    """Find metadata only beside ffmpeg or in its immediate known distribution root."""
    directory = Path(executable).resolve().parent
    candidates = [directory]
    if directory.name.lower() == "bin":
        candidates.append(directory.parent)
    for candidate_dir in candidates:
        for name in names:
            candidate = candidate_dir / name
            if candidate.is_file():
                return candidate
    return None
