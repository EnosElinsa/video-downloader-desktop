"""Compatibility launcher for the PySide6 desktop application.

The filename is retained for people who have existing shortcuts or scripts.
New users should launch the application with ``python -m desktop_app``.
"""

from desktop_app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
