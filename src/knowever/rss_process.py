from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Set, Any, Tuple, List

from .config import Config
from .paths import Paths
from .process_feed import process_article

LOG = logging.getLogger(__name__)


def load_history(path: Path) -> Set[str]:
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
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": entry_id}, ensure_ascii=False) + "\n")


def iter_feed_files(paths: Paths) -> list[Path]:
    if not paths.feeds_dir.exists():
        return []
    return sorted(paths.feeds_dir.glob("*.jsonl"))


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
            if isinstance(obj, dict):
                yield obj


def iter_entries_round_robin(files: list[Path]) -> Iterable[tuple[Path, Dict[str, Any]]]:
    active: list[tuple[Path, Iterable[Dict[str, Any]]]] = [
        (path, iter(iter_entries_from_file(path))) for path in files
    ]
    while active:
        next_active: list[tuple[Path, Iterable[Dict[str, Any]]]] = []
        for path, it in active:
            try:
                entry = next(it)
            except StopIteration:
                continue
            yield path, entry
            next_active.append((path, it))
        active = next_active


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
    score = 0.0
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

    points, comments = parse_points_comments(entry)
    if points >= 50:
        score += 3
    elif points >= 20:
        score += 1
    if comments >= 20:
        score += 2
    elif comments >= 5:
        score += 1

    content = entry.get("content") or ""
    if len(content) < 400:
        score -= 2
    elif len(content) > 1200:
        score += 1

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


def load_buffer_counts(paths: Paths) -> tuple[int, Dict[str, int]]:
    if not paths.daily_buffer.exists():
        return 0, {}
    current = today_str()
    total = 0
    per_source: Dict[str, int] = {}
    with paths.daily_buffer.open("r", encoding="utf-8") as f:
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


def load_profiles(paths: Paths) -> list[dict]:
    if not paths.profile_file.exists():
        raise FileNotFoundError(f"Profile file missing: {paths.profile_file}")
    import yaml

    with paths.profile_file.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list) or not data:
        raise ValueError("profile.yaml must contain a list of profiles")
    return data


def choose_profile(profiles: list[dict], name: str | None) -> dict:
    if name:
        for p in profiles:
            if p.get("name") == name:
                return p
    return profiles[0]


def process_all(paths: Paths, cfg: Config) -> None:
    paths.process_root.mkdir(parents=True, exist_ok=True)
    profiles = load_profiles(paths)
    profile = choose_profile(profiles, cfg.profile_name)
    min_score = float(profile.get("min_score", 0))
    max_per_source = int(profile.get("max_per_source", 2))

    global_count, per_source_counts = load_buffer_counts(paths)
    remaining_global = max(0, cfg.max_posts_per_day - global_count)
    if remaining_global <= 0:
        print("Today's MAX_POSTS_PER_DAY limit is already used - nothing to do.")
        return

    processed_ids = load_history(paths.history_path)
    feed_files = iter_feed_files(paths)
    if not feed_files:
        print("No files found in 'feeds/' directory. Run download first.")
        return

    print("== Collecting candidates from all feeds")
    candidates: list[tuple[float, Dict[str, Any], str]] = []

    for feed_file, entry in iter_entries_round_robin(feed_files):
        entry_id = str(entry.get("id", ""))
        if not entry_id:
            continue
        if entry_id in processed_ids:
            continue

        score = compute_score(entry, profile)
        if score < min_score:
            append_to_history(paths.history_path, entry_id)
            processed_ids.add(entry_id)
            continue

        candidates.append((score, entry, feed_file.name))

    if not candidates:
        print("No new candidates meet the thresholds.")
        return

    candidates.sort(key=lambda t: t[0], reverse=True)
    to_process: list[tuple[str, Path, Dict[str, Any], float, str]] = []
    selected_source_counts = dict(per_source_counts)

    for score, entry, feed_name in candidates:
        if len(to_process) >= remaining_global:
            break
        source = entry.get("source") or "?"
        if selected_source_counts.get(source, 0) >= max_per_source:
            continue
        entry_id = str(entry.get("id", ""))
        if not entry_id:
            continue
        job_dir = paths.process_root / f"job_{len(to_process)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        article_path = job_dir / "article.json"
        with article_path.open("w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        to_process.append((entry_id, job_dir, entry, score, source))
        selected_source_counts[source] = selected_source_counts.get(source, 0) + 1

    if not to_process:
        print("No candidate fits daily / per-source limits.")
        return

    workers = max(1, cfg.process_workers)
    print(f"== Processing {len(to_process)} entries (workers={workers})")

    def process_job(entry_id: str, job_dir: Path, entry: Dict[str, Any], score: float, profile_name: str) -> tuple[str, bool]:
        try:
            process_article(entry, job_dir, score, profile_name, cfg, paths)
            ok = True
        except Exception as exc:
            print(f"   !! Error during process_feed for id={entry_id}: {exc}")
            ok = False
        return entry_id, ok

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(process_job, entry_id, job_dir, entry, score, str(profile.get("name", "default")))
            for entry_id, job_dir, entry, score, source in to_process
        ]
        for fut in as_completed(futures):
            entry_id, ok = fut.result()
            if ok:
                append_to_history(paths.history_path, entry_id)
                processed_ids.add(entry_id)
