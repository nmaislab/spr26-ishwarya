from __future__ import annotations

from pathlib import Path


_REPO_MARKERS = ("src", "scripts", "data", "requirements.txt")


def find_project_root(start: str | Path | None = None) -> Path:
    """Find the repository root by structure rather than directory name."""
    current = Path(start if start is not None else __file__).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if all((candidate / marker).exists() for marker in _REPO_MARKERS):
            return candidate
    raise FileNotFoundError(
        f"Could not find project root from {current}; expected markers: {', '.join(_REPO_MARKERS)}"
    )


PROJECT_ROOT = find_project_root(__file__)


def resolve_existing_path(value: str | Path, *, base_dir: str | Path | None = None, kind: str = "path") -> Path:
    """Resolve absolute paths, cwd-relative paths, or project-root-relative paths."""
    path = Path(value).expanduser()
    base = Path(base_dir).expanduser().resolve() if base_dir is not None else Path.cwd()
    candidates = [path] if path.is_absolute() else [base / path, PROJECT_ROOT / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Missing {kind}: {path} (checked: {checked})")


def resolve_output_path(value: str | Path, *, base_dir: str | Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    base = Path(base_dir).expanduser().resolve() if base_dir is not None else Path.cwd()
    return (base / path).resolve()
