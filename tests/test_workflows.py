"""Contract tests for the GitHub Actions CI and release workflows."""

from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal local envs
    yaml = None


ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _load_workflow(name: str) -> dict:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.load(text, Loader=yaml.BaseLoader)
    # Keep the contract tests runnable without a third-party YAML package. This
    # parser intentionally covers the small mapping/list/block-scalar subset
    # used by our workflows; CI installs PyYAML from requirements-dev.txt.
    lines = text.splitlines()

    def scalar(value: str):
        value = value.strip()
        if value in {"true", "false"}:
            return value == "true"
        if value.startswith(("\"", "'")) and value.endswith(value[0]):
            return value[1:-1]
        if value.startswith("[") and value.endswith("]"):
            return [scalar(item) for item in value[1:-1].split(",") if item.strip()]
        return value

    def parse_block(start: int, indent: int):
        is_list = lines[start].startswith(" " * indent + "-")
        result = [] if is_list else {}
        index = start
        while index < len(lines):
            raw = lines[index]
            if not raw.strip() or raw.lstrip().startswith("#"):
                index += 1
                continue
            current_indent = len(raw) - len(raw.lstrip())
            if current_indent < indent:
                break
            if current_indent > indent:
                break
            content = raw[indent:]
            if is_list:
                if not content.startswith("- "):
                    break
                item = content[2:].strip()
                if ":" in item:
                    key, value = item.split(":", 1)
                    entry = {key.strip(): scalar(value)} if value.strip() else {key.strip(): None}
                    index += 1
                    if index < len(lines) and len(lines[index]) - len(lines[index].lstrip()) > indent:
                        nested, index = parse_block(index, len(lines[index]) - len(lines[index].lstrip()))
                        if entry[key.strip()] is None:
                            entry[key.strip()] = nested
                        elif isinstance(nested, dict):
                            entry.update(nested)
                    result.append(entry)
                else:
                    result.append(scalar(item))
                    index += 1
            else:
                key, value = content.split(":", 1)
                key = key.strip().strip("\"'")
                value = value.strip()
                index += 1
                if value == "|":
                    block = []
                    while index < len(lines) and (not lines[index].strip() or len(lines[index]) - len(lines[index].lstrip()) > indent):
                        block.append(lines[index].strip())
                        index += 1
                    result[key] = "\n".join(block)
                elif value:
                    result[key] = scalar(value)
                elif index < len(lines) and len(lines[index]) - len(lines[index].lstrip()) > indent:
                    result[key], index = parse_block(index, len(lines[index]) - len(lines[index].lstrip()))
                else:
                    result[key] = {}
        return result, index

    first = next(i for i, line in enumerate(lines) if line.strip() and not line.lstrip().startswith("#"))
    return parse_block(first, len(lines[first]) - len(lines[first].lstrip()))[0]


def _on(workflow: dict) -> dict:
    # YAML 1.1 parsers may interpret the unquoted ``on`` key as a boolean.
    return workflow.get("on") or workflow.get(True)


def _steps(workflow: dict) -> list[dict]:
    return [step for job in workflow["jobs"].values() for step in job.get("steps", [])]


def test_ci_runs_on_push_and_pull_request_with_python_311_windows_runner():
    workflow = _load_workflow("ci.yml")

    triggers = _on(workflow)
    assert "push" in triggers
    assert "pull_request" in triggers
    assert any(job["runs-on"] == "windows-latest" for job in workflow["jobs"].values())

    setup_python = next(step for step in _steps(workflow) if step.get("uses", "").startswith("actions/setup-python@"))
    assert setup_python["with"]["python-version"] == "3.11"

    commands = "\n".join(step.get("run", "") for step in _steps(workflow))
    assert "requirements-desktop.txt" in commands
    assert "requirements-dev.txt" in commands
    assert "python -m compileall desktop_app" in commands
    assert "python -m pytest" in commands
    assert any(step.get("env", {}).get("QT_QPA_PLATFORM") == "offscreen" for step in _steps(workflow))


def test_release_is_tagged_windows_release_with_write_permission_and_artifacts():
    workflow = _load_workflow("release.yml")

    triggers = _on(workflow)
    assert triggers["push"]["tags"] == ["v*.*.*"]
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"]["contents"] == "write"
    assert any(job["runs-on"] == "windows-latest" for job in workflow["jobs"].values())

    commands = "\n".join(step.get("run", "") for step in _steps(workflow))
    assert "build_windows.ps1" in commands
    assert "packaging/smoke_test.py" in commands

    release_step = next(
        step for step in _steps(workflow) if step.get("uses", "").startswith("softprops/action-gh-release@")
    )
    assert release_step["uses"] == "softprops/action-gh-release@v3"
    assert str(release_step["with"]["fail_on_unmatched_files"]).lower() == "true"
    files = release_step["with"]["files"]
    for artifact in (
        "dist/VideoDownloader-windows-x64.zip",
        "dist/VideoDownloader-windows-x64.exe",
        "dist/SHA256SUMS.txt",
    ):
        assert artifact in files

    build_script = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    for artifact_name in (
        "VideoDownloader-windows-x64.zip",
        "VideoDownloader-windows-x64.exe",
        "SHA256SUMS.txt",
    ):
        assert artifact_name in build_script

    build_step = next(step for step in _steps(workflow) if "build_windows.ps1" in step.get("run", ""))
    assert build_step["env"]["QT_QPA_PLATFORM"] == "offscreen"
