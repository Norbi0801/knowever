from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .paths import Paths


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class Config:
    feed_download_workers: int = 4
    process_workers: int = 2
    send_workers: int = 3
    max_posts_per_day: int = 10
    include_ai_content: bool = True
    auto_send_digest: bool = False
    send_mode: str = "digest"  # or "individual"
    clear_buffer_after_send: bool = True
    fail_ttl_seconds: int = 24 * 3600
    profile_name: Optional[str] = None
    entry_score_default: float = 0.0

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_to: str = "norbertolkowski@gmail.com"


def load_config(paths: Paths) -> Config:
    env_path = paths.root / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    cfg = Config()

    cfg.feed_download_workers = int(os.getenv("FEED_DOWNLOAD_WORKERS", cfg.feed_download_workers))
    cfg.process_workers = int(os.getenv("PROCESS_WORKERS", cfg.process_workers))
    cfg.send_workers = int(os.getenv("SEND_WORKERS", cfg.send_workers))
    cfg.max_posts_per_day = int(os.getenv("MAX_POSTS_PER_DAY", cfg.max_posts_per_day))
    cfg.include_ai_content = _to_bool(os.getenv("INCLUDE_AI_CONTENT"), cfg.include_ai_content)
    cfg.auto_send_digest = _to_bool(os.getenv("AUTO_SEND_DIGEST"), cfg.auto_send_digest)
    cfg.send_mode = os.getenv("SEND_MODE", cfg.send_mode).lower()
    cfg.clear_buffer_after_send = _to_bool(os.getenv("CLEAR_BUFFER_AFTER_SEND"), cfg.clear_buffer_after_send)
    cfg.fail_ttl_seconds = int(os.getenv("FAIL_TTL_SECONDS", cfg.fail_ttl_seconds))
    cfg.profile_name = os.getenv("PROFILE_NAME") or None
    cfg.entry_score_default = float(os.getenv("ENTRY_SCORE", cfg.entry_score_default))

    cfg.smtp_host = os.getenv("SMTP_HOST", cfg.smtp_host)
    cfg.smtp_port = int(os.getenv("SMTP_PORT", cfg.smtp_port))
    cfg.smtp_user = os.getenv("SMTP_USER", cfg.smtp_user)
    cfg.smtp_pass = os.getenv("SMTP_PASS", cfg.smtp_pass)
    cfg.smtp_from = os.getenv("SMTP_FROM", cfg.smtp_from)
    cfg.smtp_to = os.getenv("SMTP_TO", cfg.smtp_to)

    return cfg
