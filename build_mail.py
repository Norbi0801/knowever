"""
Buduje finalną treść maila na podstawie:

- listy wpisów (dict) przygotowanych do digestu,
- szablonu `email_template.html`.

Ustawienia SMTP ze zmiennych środowiskowych:
- SMTP_HOST (domyślnie: smtp.gmail.com)
- SMTP_PORT (domyślnie: 587)
- SMTP_USER (wymagane)
- SMTP_PASS (wymagane)
- SMTP_FROM (domyślnie: SMTP_USER)
- SMTP_TO (domyślnie: norbertolkowski@gmail.com)
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
import os
import smtplib
from typing import List, Dict

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

# Automatycznie wczytaj zmienne z .env w katalogu projektu,
# żeby nie trzeba było ich eksportować ręcznie.
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
PROCESS_DIR = BASE_DIR / "actual_process_feed"
TEMPLATE_PATH = BASE_DIR / "email_template.html"


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Brak pliku szablonu {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_mail_html(
    items: List[Dict],
    digest_title: str,
    digest_time: str,
    include_ai_content: bool = True,
) -> tuple[str, dict]:
    """Renderuje HTML dla wielu wpisów (digest lub pojedynczy)."""
    template = load_template()

    # Zbiorcze TL;DR: lista tytułów
    summary_lines = []
    for idx, item in enumerate(items, start=1):
        title = item.get("title") or "Bez tytułu"
        source = item.get("source") or "?"
        summary_lines.append(f"{idx}. [{source}] {title}")
    summary_text = "<br>".join(summary_lines) if summary_lines else "Brak wpisów w dzisiejszym digestzie."

    # Treść dla każdego wpisu
    item_blocks = []
    for item in items:
        title = item.get("title") or "Bez tytułu"
        url = item.get("url") or ""
        source = item.get("source") or "?"
        published = item.get("published") or ""
        content_html = item.get("content_html") or ""
        if not include_ai_content:
            # fallback: krótki opis z summary lub content (jeśli dostępny)
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

    mail_html = template
    mail_html = mail_html.replace("{{title}}", digest_title)
    mail_html = mail_html.replace("{{time}}", digest_time)
    mail_html = mail_html.replace("{{source}}", "Daily Digest")
    mail_html = mail_html.replace("{{url}}", url_placeholder or "#")
    mail_html = mail_html.replace("{{summary}}", summary_text)
    mail_html = mail_html.replace("{{content_html}}", content_html)

    meta = {
        "title": digest_title,
        "source": "Daily Digest",
        "published": digest_time,
    }

    return mail_html, meta


def send_mail(html: str, subject: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user
    smtp_to = os.getenv("SMTP_TO", "norbertolkowski@gmail.com")

    if not smtp_user or not smtp_pass:
        raise RuntimeError(
            "Brak SMTP_USER / SMTP_PASS w środowisku. "
            "Ustaw te zmienne, aby wysyłać maile."
        )
    if not smtp_from:
        raise RuntimeError("Nie udało się ustalić adresu nadawcy (SMTP_FROM / SMTP_USER).")

    subject = subject or "[NEWSFEED]"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = smtp_to
    msg.set_content("Ten mail zawiera wersję HTML. Jeśli to widzisz, klient nie obsługuje HTML.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        print(f"[build_mail] Wysłano mail na {smtp_to} (Subject: {subject})")


def main() -> None:
    print("Uruchom send_digest.py, aby zbudować i wysłać dzienny digest.")


if __name__ == "__main__":
    main()
