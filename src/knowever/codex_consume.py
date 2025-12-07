from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .paths import Paths


def run_codex(process_dir: Path, paths: Paths, prompt_path: Path | None = None) -> Path:
    """
    Run `codex exec` with prompt.md and save output.html in process_dir.
    Returns the path to output.html.
    """
    if prompt_path is None:
        prompt_path = paths.prompt_file

    if not prompt_path.exists():
        raise FileNotFoundError(f"Missing prompt file {prompt_path}")

    prompt = prompt_path.read_text(encoding="utf-8")

    local_home = process_dir / ".codex_home"
    local_cache = paths.root / ".cache"
    local_state = paths.root / ".local" / "state"
    local_home.mkdir(parents=True, exist_ok=True)
    local_cache.mkdir(parents=True, exist_ok=True)
    local_state.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(local_home)
    env.setdefault("XDG_CACHE_HOME", str(local_cache))
    env.setdefault("XDG_STATE_HOME", str(local_state))

    cmd = ["codex", "exec", "--skip-git-repo-check"]
    result = subprocess.run(
        cmd,
        input=prompt,
        cwd=str(process_dir),
        text=True,
        capture_output=True
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"codex exec exit {result.returncode}: {stderr}")

    output_html = result.stdout
    if not output_html.strip():
        raise RuntimeError("Codex returned empty content.")

    out_path = process_dir / "output.html"
    out_path.write_text(output_html, encoding="utf-8")
    return out_path
