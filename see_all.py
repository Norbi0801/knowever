"""
Skrypt pomocniczy, który oznacza wszystkie wpisy z feedów jako
"przetworzone" – dopisuje ich `id` do `feeds_process_history.jsonl`.

Nie uruchamia żadnego przetwarzania (Codex, mail, itp.), tylko aktualizuje
historię.

Użycie:
    uv run see_all.py
"""

from __future__ import annotations

from pathlib import Path

from rss_process import (
    HISTORY_PATH,
    append_to_history,
    iter_entries_from_file,
    iter_feed_files,
    load_history,
)


def main() -> None:
    # Wczytaj istniejącą historię przetworzonych wpisów.
    processed_ids = load_history(HISTORY_PATH)

    feed_files = iter_feed_files()
    if not feed_files:
        print("Brak plików w katalogu 'feeds/'. Uruchom najpierw rss_download.py.")
        return

    added = 0
    total_seen = 0

    for feed_file in feed_files:
        for entry in iter_entries_from_file(feed_file):
            total_seen += 1
            entry_id = str(entry.get("id", ""))
            if not entry_id:
                continue
            if entry_id in processed_ids:
                continue

            append_to_history(HISTORY_PATH, entry_id)
            processed_ids.add(entry_id)
            added += 1

    print(
        f"Przejrzano {total_seen} wpisów z {len(feed_files)} plików feedów."
    )
    print(
        f"Dodano {added} nowych ID do {HISTORY_PATH.name}. "
        f"Łącznie w historii: {len(processed_ids)}."
    )


if __name__ == "__main__":
    main()

