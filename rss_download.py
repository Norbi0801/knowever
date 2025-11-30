"""
Prosty downloader RSS:

- czyta listę źródeł z `sources.yaml`,
- pobiera wpisy RSS,
- zapisuje je do plików w folderze `feeds/`,
- pilnuje, żeby nie duplikować wpisów (po polu `id`).

Wymagane pakiety:
    pip install feedparser PyYAML
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set

import feedparser  # type: ignore
import yaml  # type: ignore


BASE_DIR = Path(__file__).resolve().parent
SOURCES_FILE = BASE_DIR / "sources.yaml"
FEEDS_DIR = BASE_DIR / "feeds"


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
    """Bardzo prosty slug pod nazwę pliku."""
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")


def load_sources() -> List[Dict[str, Any]]:
    if not SOURCES_FILE.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku {SOURCES_FILE}")
    with SOURCES_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError("Plik sources.yaml musi zawierać listę źródeł")
    return data


def parse_entry(source_name: str, entry) -> FeedEntry:
    entry_id = (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
        or f"{source_name}-{entry.get('title', '')}"
    )

    published = entry.get("published") or entry.get("updated") or ""
    if published and getattr(entry, "published_parsed", None):
        try:
            dt = datetime(*entry.published_parsed[:6])
            published = dt.isoformat()
        except Exception:
            # zostaw surowy string jeśli nie uda się sparsować
            pass

    # content
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
    """Wczytuje istniejące wpisy z pliku JSONL i zwraca zbiór ich ID."""
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


def append_entries(path: Path, entries: List[FeedEntry]) -> int:
    """Dopisuje nowe wpisy do pliku JSONL. Zwraca liczbę dopisanych wpisów."""
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    existing_ids = load_existing_ids(path)

    appended = 0
    with path.open("a", encoding="utf-8") as f:
        for e in entries:
            if e.id in existing_ids:
                continue
            f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
            existing_ids.add(e.id)
            appended += 1
    return appended


def download_all(verbose: bool = True) -> None:
    sources = load_sources()
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)

    for source in sources:
        name = source["name"]
        url = source["url"]
        slug = slugify(name)
        out_path = FEEDS_DIR / f"{slug}.jsonl"

        if verbose:
            print(f"== {name} ({url}) => {out_path}")

        feed = feedparser.parse(url)
        entries = [parse_entry(name, entry) for entry in feed.entries]

        added = append_entries(out_path, entries)
        if verbose:
            print(f"   dodano {added} nowych wpisów (łącznie w pliku: {len(load_existing_ids(out_path))})")


if __name__ == "__main__":
    download_all(verbose=True)

