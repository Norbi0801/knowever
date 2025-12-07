from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

from .paths import Paths
from .rss_process import iter_feed_files, iter_entries_from_file, load_history, append_to_history


def mark_all(paths: Paths) -> tuple[int, int]:
    """
    Mark every entry in feeds/ as processed (append ids to history).
    Returns (added, total_seen).
    """
    processed_ids = load_history(paths.history_path)
    feed_files = iter_feed_files(paths)
    if not feed_files:
        return 0, 0

    added = 0
    total_seen = 0
    for feed_file in feed_files:
        for entry in iter_entries_from_file(feed_file):
            total_seen += 1
            entry_id = str(entry.get("id", ""))
            if not entry_id or entry_id in processed_ids:
                continue
            append_to_history(paths.history_path, entry_id)
            processed_ids.add(entry_id)
            added += 1
    return added, total_seen
