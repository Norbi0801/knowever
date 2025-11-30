"""
Przetwarzanie wpisów z RSS:

- czyta wszystkie pliki z katalogu `feeds/` (JSONL),
- dla każdego wpisu o `id`, którego nie ma w `feeds_process_history.jsonl`,
  kopiuje cały obiekt do `actual_process_feed/article.json`,
- uruchamia skrypt `process_feed.py`,
- po zakończeniu usuwa `article.json` i dopisuje `id` do historii,
- przechodzi do następnego wpisu / feedu.

Założenia:
- `process_feed.py` znajduje się w tym samym katalogu co ten plik
  i czyta `actual_process_feed/article.json`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Set, Any


BASE_DIR = Path(__file__).resolve().parent
FEEDS_DIR = BASE_DIR / "feeds"
PROCESS_DIR = BASE_DIR / "actual_process_feed"
ARTICLE_PATH = PROCESS_DIR / "article.json"
HISTORY_PATH = BASE_DIR / "feeds_process_history.jsonl"
PROCESS_SCRIPT = BASE_DIR / "process_feed.py"


@dataclass
class ProcessedEntry:
    id: str


def load_history(path: Path) -> Set[str]:
    """Wczytuje historię przetworzonych wpisów (po `id`)."""
    processed: Set[str] = set()
    if not path.exists():
        return processed

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry_id = obj.get("id")
            if entry_id is not None:
                processed.add(str(entry_id))

    return processed


def append_to_history(path: Path, entry_id: str) -> None:
    """Dopisuje `id` przetworzonego wpisu do historii."""
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": entry_id}, ensure_ascii=False) + "\n")


def iter_feed_files() -> list[Path]:
    if not FEEDS_DIR.exists():
        return []
    return sorted(FEEDS_DIR.glob("*.jsonl"))


def iter_entries_from_file(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            yield obj


def iter_entries_round_robin(files: list[Path]) -> Iterable[tuple[Path, Dict[str, Any]]]:
    """Interleave wpisy z wielu feedów w stylu round-robin.

    Zamiast przechodzić cały pierwszy feed, a potem drugi, bierzemy:
    - pierwszy wpis z pierwszego pliku,
    - pierwszy z drugiego,
    - ...
    - drugi z pierwszego,
    - drugi z drugiego,
    - itd.
    """
    # Przygotuj iteratory dla każdego pliku
    active: list[tuple[Path, Iterable[Dict[str, Any]]]] = [
        (path, iter(iter_entries_from_file(path))) for path in files
    ]

    while active:
        next_active: list[tuple[Path, Iterable[Dict[str, Any]]]] = []
        for path, it in active:
            try:
                entry = next(it)  # może podnieść StopIteration
            except StopIteration:
                continue
            yield path, entry
            # Zostaw iterator w puli, skoro jeszcze nie wyczerpany
            next_active.append((path, it))
        active = next_active


def run_process_script() -> None:
    """Uruchamia `process_feed.py` i czeka na zakończenie."""
    if not PROCESS_SCRIPT.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku {PROCESS_SCRIPT}")

    result = subprocess.run(
        [sys.executable, str(PROCESS_SCRIPT)],
        cwd=str(BASE_DIR),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"process_feed.py zakończył się kodem {result.returncode}")


def main() -> None:
    PROCESS_DIR.mkdir(parents=True, exist_ok=True)

    processed_ids = load_history(HISTORY_PATH)

    feed_files = iter_feed_files()
    if not feed_files:
        print("Brak plików w katalogu 'feeds/'. Uruchom najpierw rss_download.py.")
        return

    print("== Przetwarzanie feedów w trybie round-robin")
    for feed_file, entry in iter_entries_round_robin(feed_files):
        entry_id = str(entry.get("id", ""))
        if not entry_id:
            continue
        if entry_id in processed_ids:
            continue

        # Zapisz aktualny wpis do article.json
        with ARTICLE_PATH.open("w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        print(f"   -> Nowy wpis: {entry_id} (plik={feed_file.name}, source={entry.get('source')})")

        try:
            run_process_script()
        except Exception as exc:
            print(f"   !! Błąd podczas process_feed.py dla id={entry_id}: {exc}")
            # Nie usuwamy article.json ani nie dopisujemy historii,
            # żeby można było łatwo zdebugować problem.
            return

        # Po udanym przetworzeniu: usuwamy plik i aktualizujemy historię
        try:
            ARTICLE_PATH.unlink(missing_ok=True)
        except Exception:
            # Ignorujemy problemy z usunięciem – nie jest krytyczne.
            pass

        append_to_history(HISTORY_PATH, entry_id)
        processed_ids.add(entry_id)


if __name__ == "__main__":
    main()
