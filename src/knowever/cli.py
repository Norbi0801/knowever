from __future__ import annotations

import argparse
from datetime import datetime
import sys
import logging

from .paths import make_paths, ensure_dirs
from .config import load_config
from .logging_utils import setup_logging, env_log_level
from .rss_download import download_all
from .rss_process import process_all
from .send_digest import send_digest
from .mark_all import mark_all


def cmd_download(args) -> None:
    paths = make_paths()
    cfg = load_config(paths)
    ensure_dirs(paths)
    download_all(paths, cfg, verbose=not args.quiet)


def cmd_process(args) -> None:
    paths = make_paths()
    cfg = load_config(paths)
    ensure_dirs(paths)
    process_all(paths, cfg)


def cmd_send(args) -> None:
    paths = make_paths()
    cfg = load_config(paths)
    ensure_dirs(paths)
    send_digest(paths, cfg)


def cmd_mark_all(args) -> None:
    paths = make_paths()
    ensure_dirs(paths)
    added, total = mark_all(paths)
    print(f"Added {added} IDs (checked {total} entries).")


def cmd_run(args) -> None:
    paths = make_paths()
    cfg = load_config(paths)
    ensure_dirs(paths)

    today = datetime.now().strftime("%Y-%m-%d")
    if paths.day_lock.exists():
        try:
            last_run = paths.day_lock.read_text(encoding="utf-8").strip()
        except Exception:
            last_run = ""
        if last_run == today:
            print(f"[rss] day.lock={today} - already ran today, skipping.")
            return

    download_all(paths, cfg, verbose=not args.quiet)
    process_all(paths, cfg)
    if cfg.auto_send_digest:
        send_digest(paths, cfg)

    paths.day_lock.write_text(today + "\n", encoding="utf-8")
    print(f"[rss] Saved day.lock = {today}")


def cmd_purge_cache(args) -> None:
    paths = make_paths()
    if paths.fail_cache.exists():
        paths.fail_cache.unlink()
        print("Cleared domain error cache (fail_cache).")
    else:
        print("No fail_cache file to remove.")


def cmd_show_buffer(args) -> None:
    paths = make_paths()
    if not paths.daily_buffer.exists():
        print("daily_buffer.jsonl not found")
        return
    lines = paths.daily_buffer.read_text(encoding="utf-8").splitlines()
    print(f"Entries in buffer: {len(lines)}")
    for line in lines[: args.limit]:
        print(line)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="knowever", description="RSS -> AI -> mail pipeline CLI")
    parser.add_argument("--quiet", action="store_true", help="Less logging")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("download", help="Download RSS feeds into feeds/").set_defaults(func=cmd_download)
    sub.add_parser("process", help="Process candidates into daily_buffer").set_defaults(func=cmd_process)
    sub.add_parser("send", help="Send digest or individual emails").set_defaults(func=cmd_send)
    sub.add_parser("run", help="Full pipeline + day.lock").set_defaults(func=cmd_run)
    sub.add_parser("purge-cache", help="Clear domain error cache").set_defaults(func=cmd_purge_cache)
    sub.add_parser("mark-all", help="Mark all entries in feeds/ as processed (add to history)").set_defaults(func=cmd_mark_all)
    show = sub.add_parser("show-buffer", help="Show today's buffer")
    show.add_argument("--limit", type=int, default=5, help="How many lines to show (default 5)")
    show.set_defaults(func=cmd_show_buffer)

    return parser


def main(argv=None) -> int:
    paths = make_paths()
    setup_logging(paths, level=env_log_level())

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        args.func(args)
    except Exception as exc:
        logging.exception("Execution error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
