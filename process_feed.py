"""
Roboczy skrypt przetwarzania pojedynczego wpisu RSS.

- czyta plik `actual_process_feed/article.json`,
- wypisuje w konsoli `source` danego wpisu.

Teraz:
- uruchamia download_feed.py (pobranie content.html),
- uruchamia codex_consume.py (przetworzenie przez Codexa do output.html),
- uruchamia build_mail.py (złożenie i wysłanie maila),
- na końcu czyści zawartość katalogu `actual_process_feed/`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
import shutil


BASE_DIR = Path(__file__).resolve().parent
PROCESS_DIR = BASE_DIR / "actual_process_feed"
ARTICLE_PATH = PROCESS_DIR / "article.json"


def run_step(script: str) -> None:
    """Uruchamia podskrypt Pythona z katalogu projektu."""
    script_path = BASE_DIR / script
    if not script_path.exists():
        raise FileNotFoundError(f"Brak skryptu {script_path}")

    print(f"[process_feed] Uruchamiam: uv run {script}")
    result = subprocess.run(
        ["uv", "run", script],
        cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        raise RuntimeError(f"{script} zakończył się kodem {result.returncode}")


def clean_actual_process_feed() -> None:
    """Czyści zawartość katalogu actual_process_feed/ (ale nie usuwa samego folderu)."""
    if not PROCESS_DIR.exists():
        return
    for child in PROCESS_DIR.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def main() -> None:
    if not ARTICLE_PATH.exists():
        print(f"Brak pliku {ARTICLE_PATH} – nic do przetworzenia.")
        return

    print(f"[process_feed] Start przetwarzania {ARTICLE_PATH}")

    try:
        # 1. Pobierz pełną treść artykułu do content.html
        run_step("download_feed.py")

        # 2. Przetwórz treść przez Codexa -> output.html
        run_step("codex_consume.py")

        # 3. Zbuduj i wyślij maila
        run_step("build_mail.py")
    finally:
        # 4. Wyczyść katalog actual_process_feed
        clean_actual_process_feed()
        print("[process_feed] Wyczyściłem katalog actual_process_feed/")


if __name__ == "__main__":
    main()
