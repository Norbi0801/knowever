from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def detect_root() -> Path:
    """
    Find the repository root (where pyproject.toml lives).
    Assumes layout src/knowever/*.py => root is the parent of src.
    """
    here = Path(__file__).resolve()
    for candidate in [
        here.parent.parent.parent,  # typical: src/knowever -> src -> repo
        here.parent.parent,  # fallback gdy zainstalowane inaczej
    ]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return here.parent.parent


@dataclass(frozen=True)
class Paths:
    root: Path
    feeds_dir: Path
    process_root: Path
    tmp_dir: Path
    logs_dir: Path
    daily_buffer: Path
    history_path: Path
    sources_file: Path
    profile_file: Path
    email_template: Path
    prompt_file: Path
    fail_cache: Path
    day_lock: Path


def make_paths(root: Path | None = None) -> Paths:
    root_dir = root or detect_root()
    feeds_dir = root_dir / "feeds"
    process_root = root_dir / "actual_process_feed"
    tmp_dir = root_dir / "tmp"
    logs_dir = root_dir / "logs"
    daily_buffer = root_dir / "daily_buffer.jsonl"
    history_path = root_dir / "feeds_process_history.jsonl"
    sources_file = root_dir / "sources.yaml"
    profile_file = root_dir / "profile.yaml"
    email_template = root_dir / "email_template.html"
    prompt_file = root_dir / "prompt.md"
    fail_cache = tmp_dir / "fetch_failures.json"
    day_lock = root_dir / "day.lock"

    return Paths(
        root=root_dir,
        feeds_dir=feeds_dir,
        process_root=process_root,
        tmp_dir=tmp_dir,
        logs_dir=logs_dir,
        daily_buffer=daily_buffer,
        history_path=history_path,
        sources_file=sources_file,
        profile_file=profile_file,
        email_template=email_template,
        prompt_file=prompt_file,
        fail_cache=fail_cache,
        day_lock=day_lock,
    )


def ensure_dirs(paths: Paths) -> None:
    for p in [paths.feeds_dir, paths.process_root, paths.tmp_dir, paths.logs_dir]:
        p.mkdir(parents=True, exist_ok=True)
