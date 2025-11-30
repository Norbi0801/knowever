"""
Wysyła dzienny digest z wpisów zgromadzonych w daily_buffer.jsonl.

Użycie:
    uv run send_digest.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
from dotenv import load_dotenv

from build_mail import build_mail_html, send_mail
from rss_process import DAILY_BUFFER_PATH, PROFILE_PATH, load_profiles, choose_profile

BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


def load_today_entries():
    if not DAILY_BUFFER_PATH.exists():
        return []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = []
    with DAILY_BUFFER_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("date") != today:
                continue
            entries.append(obj)
    return entries


def flush_today(entries_sent: list) -> None:
    """Usuwa z daily_buffer wpisy z dzisiejszą datą, żeby nie wysyłać ich ponownie."""
    if not DAILY_BUFFER_PATH.exists():
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    keep_lines = []
    ids_sent = {e.get("id") for e in entries_sent}
    with DAILY_BUFFER_PATH.open("r", encoding="utf-8") as f:
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
    DAILY_BUFFER_PATH.write_text("\n".join(keep_lines) + ("\n" if keep_lines else ""), encoding="utf-8")


def main() -> None:
    profiles = load_profiles()
    profile = choose_profile(profiles)
    digest_limit = int(os.getenv("MAX_POSTS_PER_DAY", "10"))
    send_mode = os.getenv("SEND_MODE", "digest").lower()  # 'digest' lub 'individual'
    include_ai = os.getenv("INCLUDE_AI_CONTENT", "true").lower() != "false"
    clear_after_send = os.getenv("CLEAR_BUFFER_AFTER_SEND", "true").lower() != "false"

    entries = load_today_entries()
    if not entries:
        print("Brak wpisów w dzisiejszym buforze – nic do wysłania.")
        return

    # Posortuj po score malejąco
    entries.sort(key=lambda e: e.get("score", 0), reverse=True)
    entries = entries[:digest_limit]

    sent_entries = []

    if send_mode == "individual":
        workers = int(os.getenv("SEND_WORKERS", "3"))
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def send_one(item):
            digest_title = f"{item.get('title') or 'Bez tytułu'}"
            digest_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            html, _meta = build_mail_html([item], digest_title, digest_time, include_ai_content=include_ai)
            subject = f"[NEWSFEED] [{item.get('source','?')}] {item.get('title','Bez tytułu')}"
            send_mail(html, subject)
            return item

        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = [executor.submit(send_one, item) for item in entries]
            for fut in as_completed(futures):
                sent_entries.append(fut.result())
        print(f"Wysłano {len(sent_entries)} pojedynczych maili (workers={max(1, workers)}).")
    else:
        digest_title = f"Daily RSS Digest ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
        digest_time = profile.get("send_time", "17:00") + " UTC"
        html, meta = build_mail_html(entries, digest_title, digest_time, include_ai_content=include_ai)
        subject = f"[NEWSFEED] {digest_title}"
        send_mail(html, subject)
        sent_entries = entries
        print(f"Wysłano digest z {len(entries)} wpisami.")

    if clear_after_send and sent_entries:
        flush_today(sent_entries)


if __name__ == "__main__":
    main()
