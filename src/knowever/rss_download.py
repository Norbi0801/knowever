from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

import feedparser  # type: ignore
import yaml  # type: ignore

from .config import Config
from .paths import Paths

LOG = logging.getLogger(__name__)


@dataclass
class FeedEntry:
    id: str
    source: str
    title: str
    url: str
    published: str
    summary: str
    content: str


def slugify(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")


def load_sources(paths: Paths) -> List[Dict[str, Any]]:
    if not paths.sources_file.exists():
        raise FileNotFoundError(f"sources file not found: {paths.sources_file}")
    with paths.sources_file.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError("sources.yaml must contain a list of sources")
    return data


def parse_entry(source_name: str, entry) -> FeedEntry:
    entry_id = entry.get("id") or entry.get("guid") or entry.get("link") or f"{source_name}-{entry.get('title', '')}"
    published = entry.get("published") or entry.get("updated") or ""
    if published and getattr(entry, "published_parsed", None):
        try:
            dt = datetime(*entry.published_parsed[:6])
            published = dt.isoformat()
        except Exception:
            pass

    content = ""
    if "content" in entry and entry.content:
        content = " ".join(c.get("value", "") for c in entry.content)
    else:
        content = entry.get("summary", "") or ""

    return FeedEntry(
        id=str(entry_id),
        source=source_name,
        title=entry.get("title", "") or "",
        url=entry.get("link", "") or "",
        published=published,
        summary=entry.get("summary", "") or "",
        content=content,
    )


def load_existing_ids(path: Path) -> Set[str]:
    ids: Set[str] = set()
    if not path.exists():
        return ids
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
                ids.add(str(entry_id))
    return ids


def load_existing_titles(path: Path) -> List[str]:
    titles: List[str] = []
    if not path.exists():
        return titles
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            title = obj.get("title")
            if title:
                titles.append(str(title))
    return titles


def similar_title(title: str, existing: List[str], threshold: float = 0.9) -> bool:
    for other in existing:
        if not other:
            continue
        ratio = SequenceMatcher(None, title.lower(), other.lower()).ratio()
        if ratio >= threshold:
            return True
    return False


def append_entries(path: Path, entries: List[FeedEntry]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = load_existing_ids(path)
    existing_titles = load_existing_titles(path)
    appended = 0
    with path.open("a", encoding="utf-8") as f:
        for e in entries:
            if e.id in existing_ids:
                continue
            if e.title and similar_title(e.title, existing_titles):
                continue
            f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
            existing_ids.add(e.id)
            if e.title:
                existing_titles.append(e.title)
            appended += 1
    return appended


def process_source(source: Dict[str, Any], paths: Paths, verbose: bool = True) -> tuple[str, int]:
    name = source["name"]
    url = source["url"]
    slug = slugify(name)
    out_path = paths.feeds_dir / f"{slug}.jsonl"

    if verbose:
        print(f"== {name} ({url}) => {out_path}")

    feed = feedparser.parse(url)
    entries = [parse_entry(name, entry) for entry in feed.entries]

    added = append_entries(out_path, entries)
    if verbose:
        print(f"   added {added} new entries (total in file: {len(load_existing_ids(out_path))})")
    return name, added


def download_all(paths: Paths, cfg: Config, verbose: bool = True) -> None:
    sources = load_sources(paths)
    paths.feeds_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, cfg.feed_download_workers)

    if workers == 1:
        for source in sources:
            process_source(source, paths, verbose=verbose)
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_source, source, paths, verbose): source for source in sources}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                src = futures[future].get("name")
                LOG.error("Error while fetching %s: %s", src, exc)
