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
import json
from datetime import datetime, timezone
import os
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


def get_process_dir() -> Path:
    pd = os.getenv("PROCESS_DIR")
    if pd:
        return Path(pd).resolve()
    return BASE_DIR / "actual_process_feed"


PROCESS_DIR = get_process_dir()
ARTICLE_PATH = PROCESS_DIR / "article.json"
OUTPUT_PATH = PROCESS_DIR / "output.html"
DAILY_BUFFER_PATH = BASE_DIR / "daily_buffer.jsonl"


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
    PROCESS_DIR.mkdir(parents=True, exist_ok=True)
    if not ARTICLE_PATH.exists():
        print(f"Brak pliku {ARTICLE_PATH} – nic do przetworzenia.")
        return

    print(f"[process_feed] Start przetwarzania {ARTICLE_PATH}")

    try:
        article = json.loads(ARTICLE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[process_feed] Nie mogę wczytać article.json: {exc}")
        return

    include_ai = os.getenv("INCLUDE_AI_CONTENT", "true").lower() != "false"

    try:
        # 1. Pobierz pełną treść artykułu do content.html
        run_step("download_feed.py")

        # 2. Przetwórz treść przez Codexa -> output.html (lub pomiń, jeśli AI wyłączone)
        if include_ai:
            run_step("codex_consume.py")
        else:
            # Minimalny HTML na bazie summary / content
            summary = article.get("summary") or ""
            if not summary and article.get("content"):
                summary = str(article["content"])[:500] + "..."
            if not summary:
                summary = "Brak podsumowania."
            OUTPUT_PATH.write_text(f"<p>{summary}</p>", encoding="utf-8")

        # 3. Dopisz wpis do dziennego bufora
        if not OUTPUT_PATH.exists():
            print("[process_feed] Brak output.html – pomijam zapis do bufora.")
            return
        output_html = OUTPUT_PATH.read_text(encoding="utf-8")

        entry_score = float(os.getenv("ENTRY_SCORE", "0"))
        profile_name = os.getenv("PROFILE_NAME", "default")

        DAILY_BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
        buffer_entry = {
            "id": article.get("id"),
            "source": article.get("source"),
            "title": article.get("title"),
            "url": article.get("url"),
            "published": article.get("published"),
            "summary": article.get("summary"),
            "content_html": output_html,
            "score": entry_score,
            "profile": profile_name,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        with DAILY_BUFFER_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(buffer_entry, ensure_ascii=False) + "\n")
        print(f"[process_feed] Dodano wpis do {DAILY_BUFFER_PATH.name} (score={entry_score})")
    finally:
        # 4. Wyczyść katalog actual_process_feed
        clean_actual_process_feed()
        print("[process_feed] Wyczyściłem katalog actual_process_feed/")


if __name__ == "__main__":
    main()
