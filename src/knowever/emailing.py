from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import List, Dict
import os
import smtplib

from .config import Config
from .paths import Paths


def load_template(paths: Paths) -> str:
    template_path = paths.email_template
    if not template_path.exists():
        raise FileNotFoundError(f"Template file missing: {template_path}")
    return template_path.read_text(encoding="utf-8")


def build_mail_html(
    items: List[Dict],
    digest_title: str,
    digest_time: str,
    include_ai_content: bool,
    paths: Paths,
) -> tuple[str, dict]:
    template = load_template(paths)

    summary_lines = []
    for idx, item in enumerate(items, start=1):
        title = item.get("title") or "No title"
        source = item.get("source") or "?"
        summary_lines.append(f"{idx}. [{source}] {title}")
    summary_text = "<br>".join(summary_lines) if summary_lines else "No entries in today's digest."

    item_blocks = []
    for item in items:
        title = item.get("title") or "No title"
        url = item.get("url") or ""
        source = item.get("source") or "?"
        published = item.get("published") or ""
        content_html = item.get("content_html") or ""
        if not include_ai_content:
            content_html = item.get("summary") or ""
            if not content_html and item.get("content"):
                content_html = str(item["content"])[:500] + "..."
            if content_html:
                content_html = f"<p>{content_html}</p>"
        score = item.get("score", 0)

        block = f"""
        <div style="margin-bottom:24px; padding-bottom:16px; border-bottom:1px solid #e5e7eb;">
          <h2 style="font-size:18px; margin:0 0 6px 0;">{title}</h2>
          <div style="font-size:12px; color:#6b7280; margin-bottom:8px;">
            <span>{source}</span> • <span>{published}</span> • <span>score: {score:.1f}</span>
          </div>
          <div style="font-size:14px; color:#111827; margin-bottom:10px;">
            {content_html}
          </div>
          <div style="font-size:13px;"><a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a></div>
        </div>
        """
        item_blocks.append(block)

    content_html = "\n".join(item_blocks)
    url_placeholder = items[0].get("url") if items else "https://"

    mail_html = (
        template.replace("{{title}}", digest_title)
        .replace("{{time}}", digest_time)
        .replace("{{source}}", "Daily Digest")
        .replace("{{url}}", url_placeholder or "#")
        .replace("{{summary}}", summary_text)
        .replace("{{content_html}}", content_html)
    )

    meta = {
        "title": digest_title,
        "source": "Daily Digest",
        "published": digest_time,
    }

    return mail_html, meta


def send_mail(html: str, subject: str, cfg: Config) -> None:
    smtp_user = cfg.smtp_user
    smtp_pass = cfg.smtp_pass
    smtp_from = cfg.smtp_from or smtp_user
    smtp_to = cfg.smtp_to

    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP_USER/SMTP_PASS missing in configuration.")
    if not smtp_from:
        raise RuntimeError("Could not determine sender address (SMTP_FROM / SMTP_USER).")

    msg = EmailMessage()
    msg["Subject"] = subject or "[NEWSFEED]"
    msg["From"] = smtp_from
    msg["To"] = smtp_to
    msg.set_content("This email contains an HTML version. If you see this text, your client does not support HTML.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
