from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import Config
from .paths import Paths
from .emailing import build_mail_html, send_mail
from .rss_process import load_profiles, choose_profile


def _load_today_entries(paths: Paths) -> list[dict]:
    if not paths.daily_buffer.exists():
        return []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = []
    with paths.daily_buffer.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("date") == today:
                entries.append(obj)
    return entries


def _flush_today(entries_sent: list, paths: Paths) -> None:
    if not paths.daily_buffer.exists():
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    keep_lines = []
    ids_sent = {e.get("id") for e in entries_sent}
    with paths.daily_buffer.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("date") == today and obj.get("id") in ids_sent:
                continue
            keep_lines.append(json.dumps(obj, ensure_ascii=False))
    paths.daily_buffer.write_text("\n".join(keep_lines) + ("\n" if keep_lines else ""), encoding="utf-8")


def send_digest(paths: Paths, cfg: Config) -> None:
    profiles = load_profiles(paths)
    profile = choose_profile(profiles, cfg.profile_name)
    digest_limit = int(cfg.max_posts_per_day)
    send_mode = cfg.send_mode  # 'digest' or 'individual'
    include_ai = cfg.include_ai_content
    clear_after_send = cfg.clear_buffer_after_send

    entries = _load_today_entries(paths)
    if not entries:
        print("No entries in today's buffer - nothing to send.")
        return

    entries.sort(key=lambda e: e.get("score", 0), reverse=True)
    entries = entries[:digest_limit]

    sent_entries: List[dict] = []

    if send_mode == "individual":
        workers = max(1, cfg.send_workers)

        def send_one(item):
            digest_title = f"{item.get('title') or 'No title'}"
            digest_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            html, _meta = build_mail_html([item], digest_title, digest_time, include_ai, paths)
            subject = f"[NEWSFEED] [{item.get('source','?')}] {item.get('title','No title')}"
            send_mail(html, subject, cfg)
            return item

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(send_one, item) for item in entries]
            for fut in as_completed(futures):
                sent_entries.append(fut.result())
        print(f"Sent {len(sent_entries)} individual emails (workers={cfg.send_workers}).")
    else:
        digest_title = f"Daily RSS Digest ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
        digest_time = profile.get("send_time", "17:00") + " UTC"
        html, meta = build_mail_html(entries, digest_title, digest_time, include_ai, paths)
        subject = f"[NEWSFEED] {digest_title}"
        send_mail(html, subject, cfg)
        sent_entries = entries
        print(f"Sent digest with {len(entries)} entries.")

    if clear_after_send and sent_entries:
        _flush_today(sent_entries, paths)
