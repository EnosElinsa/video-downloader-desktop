from pathlib import Path


def test_desktop_dependency_files_exist():
    root = Path(__file__).parents[1]
    assert (root / "pyproject.toml").is_file()
    assert (root / "requirements-desktop.txt").is_file()
    assert (root / "requirements-dev.txt").is_file()
