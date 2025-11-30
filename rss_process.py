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
from typing import Dict, Iterable, Set, Any, Tuple, List
from datetime import datetime, timezone
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
FEEDS_DIR = BASE_DIR / "feeds"
PROCESS_DIR = BASE_DIR / "actual_process_feed"
ARTICLE_PATH = PROCESS_DIR / "article.json"
HISTORY_PATH = BASE_DIR / "feeds_process_history.jsonl"
PROCESS_SCRIPT = BASE_DIR / "process_feed.py"
DAILY_BUFFER_PATH = BASE_DIR / "daily_buffer.jsonl"
PROFILE_PATH = BASE_DIR / "profile.yaml"

# Wczytaj .env (jeśli jest), żeby zmienne typu PROCESS_WORKERS/INCLUDE_AI_CONTENT były widoczne bez exportu
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# Global limit – może być nadpisany przez .env
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "10"))


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


def run_process_script(extra_env: Dict[str, str]) -> None:
    """Uruchamia `process_feed.py` i czeka na zakończenie."""
    if not PROCESS_SCRIPT.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku {PROCESS_SCRIPT}")

    env = os.environ.copy()
    env.update(extra_env)

    result = subprocess.run(
        [sys.executable, str(PROCESS_SCRIPT)],
        cwd=str(BASE_DIR),
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"process_feed.py zakończył się kodem {result.returncode}")


def load_profiles() -> list[dict]:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(f"Brak pliku profilu {PROFILE_PATH}")
    import yaml  # local import to avoid dependency at module import time

    with PROFILE_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list) or not data:
        raise ValueError("profile.yaml musi zawierać listę profili")
    return data


def choose_profile(profiles: list[dict]) -> dict:
    """Na razie wybieramy pierwszy profil; w przyszłości można dodać zmienną środowiskową."""
    wanted = os.getenv("PROFILE_NAME")
    if wanted:
        for p in profiles:
            if p.get("name") == wanted:
                return p
    return profiles[0]


def parse_points_comments(entry: Dict[str, Any]) -> tuple[int, int]:
    summary = entry.get("summary", "") or ""
    points = 0
    comments = 0
    m_points = re.search(r"Points:\s*(\d+)", summary, re.IGNORECASE)
    m_comments = re.search(r"#\s*Comments:\s*(\d+)", summary, re.IGNORECASE)
    if m_points:
        points = int(m_points.group(1))
    if m_comments:
        comments = int(m_comments.group(1))
    return points, comments


def compute_score(entry: Dict[str, Any], profile: Dict[str, Any]) -> float:
    """Prosty scoring na podstawie świeżości, punktów i słów kluczy."""
    score = 0.0

    # 1) Świeżość
    published = entry.get("published") or ""
    if published:
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - dt
            hours = age.total_seconds() / 3600
            if hours <= 24:
                score += 3
            elif hours <= 48:
                score += 1
            else:
                score -= 3
        except Exception:
            score -= 1

    # 2) HN/Reddit sygnały (punkty, komentarze)
    points, comments = parse_points_comments(entry)
    if points >= 50:
        score += 3
    elif points >= 20:
        score += 1
    if comments >= 20:
        score += 2
    elif comments >= 5:
        score += 1

    # 3) Długość treści (lekki filtr na bardzo krótkie)
    content = entry.get("content") or ""
    if len(content) < 400:
        score -= 2
    elif len(content) > 1200:
        score += 1

    # 4) Słowa kluczowe
    text = f"{entry.get('title','')} {entry.get('summary','')}".lower()
    positives = [kw.lower() for kw in profile.get("keywords_positive", [])]
    negatives = [kw.lower() for kw in profile.get("keywords_negative", [])]
    for kw in positives:
        if kw and kw in text:
            score += 2
    for kw in negatives:
        if kw and kw in text:
            score -= 3

    return score


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_buffer_counts() -> tuple[int, Dict[str, int]]:
    """Zwraca (global_count_today, per_source_counts_today)."""
    if not DAILY_BUFFER_PATH.exists():
        return 0, {}
    current = today_str()
    total = 0
    per_source: Dict[str, int] = {}
    with DAILY_BUFFER_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("date") != current:
                continue
            total += 1
            src = obj.get("source") or "?"
            per_source[src] = per_source.get(src, 0) + 1
    return total, per_source


def main() -> None:
    PROCESS_DIR.mkdir(parents=True, exist_ok=True)

    profiles = load_profiles()
    profile = choose_profile(profiles)
    min_score = float(profile.get("min_score", 0))
    max_per_source = int(profile.get("max_per_source", 2))

    global_count, per_source_counts = load_buffer_counts()
    remaining_global = max(0, MAX_POSTS_PER_DAY - global_count)
    if remaining_global <= 0:
        print("Dzisiejszy limit MAX_POSTS_PER_DAY został już wyczerpany – nic do zrobienia.")
        return

    processed_ids = load_history(HISTORY_PATH)

    feed_files = iter_feed_files()
    if not feed_files:
        print("Brak plików w katalogu 'feeds/'. Uruchom najpierw rss_download.py.")
        return

    print("== Zbieram kandydatów ze wszystkich feedów")

    candidates: list[tuple[float, Dict[str, Any], str]] = []  # (score, entry, feed_file_name)

    for feed_file, entry in iter_entries_round_robin(feed_files):
        entry_id = str(entry.get("id", ""))
        if not entry_id:
            continue
        if entry_id in processed_ids:
            continue

        score = compute_score(entry, profile)
        source = entry.get("source") or "?"

        if score < min_score:
            append_to_history(HISTORY_PATH, entry_id)
            processed_ids.add(entry_id)
            continue

        # per-source history counts already include today's buffer;
        # wybór zrobimy po posortowaniu, żeby brać najlepsze.
        candidates.append((score, entry, feed_file.name))

    if not candidates:
        print("Brak nowych kandydatów spełniających progi.")
        return

    # sortuj malejąco po score
    candidates.sort(key=lambda t: t[0], reverse=True)

    to_process: list[tuple[str, Path, Dict[str, Any], float, str]] = []
    selected_source_counts = dict(per_source_counts)  # copy to track selection

    for score, entry, feed_name in candidates:
        if len(to_process) >= remaining_global:
            break
        source = entry.get("source") or "?"
        if selected_source_counts.get(source, 0) >= max_per_source:
            continue

        entry_id = str(entry.get("id", ""))
        if not entry_id:
            continue

        job_dir = PROCESS_DIR / f"job_{len(to_process)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        article_path = job_dir / "article.json"
        with article_path.open("w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        to_process.append((entry_id, job_dir, entry, score, source))
        selected_source_counts[source] = selected_source_counts.get(source, 0) + 1

    if not to_process:
        print("Żaden kandydat nie mieści się w limitach dziennych / per-source.")
        return

    workers = int(os.getenv("PROCESS_WORKERS", "2"))
    if workers < 1:
        workers = 1

    def process_job(entry_id: str, job_dir: Path, score: float, profile_name: str) -> tuple[str, bool, str]:
        try:
            run_process_script(
                {
                    "ENTRY_SCORE": str(score),
                    "PROFILE_NAME": profile_name,
                    "PROCESS_DIR": str(job_dir),
                }
            )
            ok = True
        except Exception as exc:
            print(f"   !! Błąd podczas process_feed.py dla id={entry_id}: {exc}")
            ok = False
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)
        return entry_id, ok, str(job_dir)

    if to_process:
        print(f"== Uruchamiam przetwarzanie {len(to_process)} wpisów (workers={workers})")
    else:
        print("Brak nowych wpisów spełniających progi.")
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(process_job, entry_id, job_dir, score, str(profile.get("name", "default")))
            for entry_id, job_dir, entry, score, source in to_process
        ]
        for fut in as_completed(futures):
            entry_id, ok, _ = fut.result()
            if ok:
                append_to_history(HISTORY_PATH, entry_id)
                processed_ids.add(entry_id)


if __name__ == "__main__":
    main()
