"""Exercise the frozen application's display-free version path."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--expected-version")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    executable = args.exe.resolve()
    if not executable.is_file():
        print(f"Smoke test executable does not exist: {executable}", file=sys.stderr)
        return 2

    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Could not run --version: {error}", file=sys.stderr)
        return 1

    output = (result.stdout or "").strip()
    error_output = (result.stderr or "").strip()
    if result.returncode != 0:
        print(f"--version exited with {result.returncode}: {error_output}", file=sys.stderr)
        return 1
    if not output.startswith("Video Downloader "):
        print(f"Unexpected --version output: {output!r}", file=sys.stderr)
        return 1
    if args.expected_version and output != f"Video Downloader {args.expected_version}":
        print(
            f"Expected Video Downloader {args.expected_version!s}, got {output!r}",
            file=sys.stderr,
        )
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
