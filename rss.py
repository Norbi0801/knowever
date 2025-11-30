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
import os
from datetime import datetime
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

DAY_LOCK_PATH = BASE_DIR / "day.lock"


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
    today = datetime.now().strftime("%Y-%m-%d")

    if DAY_LOCK_PATH.exists():
        try:
            last_run = DAY_LOCK_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            last_run = ""
        if last_run == today:
            print(f"[rss] day.lock={today} – już uruchomione dziś, pomijam.")
            return

    # 1. Odśwież feedy
    run_step("rss_download.py")

    # 2. Przetwórz wszystkie nowe wpisy
    run_step("rss_process.py")

    # 3. Opcjonalnie wyślij digest/maile jeśli ustawiono AUTO_SEND_DIGEST=true
    if os.getenv("AUTO_SEND_DIGEST", "false").lower() == "true":
        run_step("send_digest.py")

    # 4. Zapisz znacznik dnia
    DAY_LOCK_PATH.write_text(today + "\n", encoding="utf-8")
    print(f"[rss] Zapisano day.lock = {today}")


if __name__ == "__main__":
    main()
