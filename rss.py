"""
Prosty entrypoint do całego pipeline'u RSS:

1. `rss_download.py` – aktualizuje feedy w katalogu `feeds/`.
2. `rss_process.py`  – przechodzi po wszystkich nowych wpisach
   (round-robin po feedach) i dla każdego:
     - zapisuje article.json,
     - pobiera pełny HTML,
     - przepuszcza przez Codexa,
     - buduje i wysyła maila,
     - czyści `actual_process_feed/`.

Użycie:
    uv run rss.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def run_step(script: str) -> None:
    script_path = BASE_DIR / script
    if not script_path.exists():
        raise FileNotFoundError(f"Brak skryptu {script_path}")

    print(f"[rss] Uruchamiam: uv run {script}")
    result = subprocess.run(
        ["uv", "run", script],
        cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        raise RuntimeError(f"{script} zakończył się kodem {result.returncode}")


def main() -> None:
    # 1. Odśwież feedy
    run_step("rss_download.py")

    # 2. Przetwórz wszystkie nowe wpisy
    run_step("rss_process.py")


if __name__ == "__main__":
    main()

