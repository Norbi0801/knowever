from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
import logging

from .config import Config
from .paths import Paths
from .download_feed import download_article, remember_fail
from .codex_consume import run_codex

LOG = logging.getLogger(__name__)


def _write_buffer_entry(
    article: dict, output_html: str, score: float, profile_name: str, paths: Paths
) -> None:
    entry = {
        "id": article.get("id"),
        "source": article.get("source"),
        "title": article.get("title"),
        "url": article.get("url"),
        "published": article.get("published"),
        "summary": article.get("summary"),
        "content_html": output_html,
        "score": score,
        "profile": profile_name,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    paths.daily_buffer.parent.mkdir(parents=True, exist_ok=True)
    with paths.daily_buffer.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def process_article(
    article: dict,
    process_dir: Path,
    score: float,
    profile_name: str,
    cfg: Config,
    paths: Paths,
) -> None:
    """
    Fetch content, optionally run it through Codex, and write to daily_buffer.
    process_dir is unique per job and is cleaned up afterwards.
    """
    process_dir.mkdir(parents=True, exist_ok=True)

    try:
        try:
            content_path = download_article(article, process_dir, paths, cfg)
        except Exception as exc:
            remember_fail(article.get("url", ""), paths)
            raise

        output_html = ""
        if cfg.include_ai_content:
            output_path = run_codex(process_dir, paths)
            output_html = output_path.read_text(encoding="utf-8")
        else:
            summary = article.get("summary") or ""
            if not summary and article.get("content"):
                summary = str(article["content"])[:500] + "..."
            output_html = f"<p>{summary}</p>"

        if not output_html:
            raise RuntimeError("No content to write to buffer.")

        _write_buffer_entry(article, output_html, score, profile_name, paths)
        LOG.info("Added entry %s to daily_buffer", article.get("id"))
    finally:
        shutil.rmtree(process_dir, ignore_errors=True)
