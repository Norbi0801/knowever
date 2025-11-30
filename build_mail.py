"""
Buduje finalną treść maila na podstawie:

- `actual_process_feed/article.json`  (dane wpisu RSS),
- `actual_process_feed/output.html`   (zredagowana treść od Codexa),
- szablonu `email_template.html`.

Zamiast zapisywać plik, wysyła mail na adres
`norbertolkowski@gmail.com`.

Temat maila:
    [NEWSFEED] [SOURCE] - title

Ustawienia SMTP pobiera ze zmiennych środowiskowych:
- SMTP_HOST (domyślnie: smtp.gmail.com)
- SMTP_PORT (domyślnie: 587)
- SMTP_USER (wymagane)
- SMTP_PASS (wymagane)
- SMTP_FROM (domyślnie: SMTP_USER)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import os
import smtplib

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

# Automatycznie wczytaj zmienne z .env w katalogu projektu,
# żeby nie trzeba było ich eksportować ręcznie.
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
PROCESS_DIR = BASE_DIR / "actual_process_feed"
TEMPLATE_PATH = BASE_DIR / "email_template.html"
ARTICLE_PATH = PROCESS_DIR / "article.json"
CONTENT_PATH = PROCESS_DIR / "output.html"


def load_article() -> dict:
    if not ARTICLE_PATH.exists():
        raise FileNotFoundError(f"Brak pliku {ARTICLE_PATH}")
    with ARTICLE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_content_html() -> str:
    if not CONTENT_PATH.exists():
        raise FileNotFoundError(f"Brak pliku {CONTENT_PATH} – uruchom najpierw Codexa, żeby wygenerować output.html.")
    return CONTENT_PATH.read_text(encoding="utf-8")


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Brak pliku szablonu {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_mail_html() -> tuple[str, dict]:
    article = load_article()
    content_html = load_content_html()
    template = load_template()

    title = article.get("title") or "Bez tytułu"
    published = article.get("published") or ""
    # Fallback na aktualny czas, jeśli brak daty w artykule
    if not published:
        published = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    source = article.get("source") or "Nieznane źródło"
    url = article.get("url") or ""

    raw_summary = article.get("summary") or ""
    # Lekki fallback: jeśli summary jest puste, spróbuj wziąć początek contentu
    if not raw_summary and article.get("content"):
        raw_summary = str(article["content"])[:280] + "..."

    mail_html = template
    mail_html = mail_html.replace("{{title}}", title)
    mail_html = mail_html.replace("{{time}}", published)
    mail_html = mail_html.replace("{{source}}", source)
    mail_html = mail_html.replace("{{url}}", url)
    mail_html = mail_html.replace("{{summary}}", raw_summary)
    mail_html = mail_html.replace("{{content_html}}", content_html)

    meta = {
        "title": title,
        "source": source,
        "url": url,
        "published": published,
    }

    return mail_html, meta


def send_mail(html: str, meta: dict) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user
    smtp_to = "norbertolkowski@gmail.com"

    if not smtp_user or not smtp_pass:
        raise RuntimeError(
            "Brak SMTP_USER / SMTP_PASS w środowisku. "
            "Ustaw te zmienne, aby wysyłać maile."
        )
    if not smtp_from:
        raise RuntimeError("Nie udało się ustalić adresu nadawcy (SMTP_FROM / SMTP_USER).")

    subject = f"[NEWSFEED] [{meta.get('source', 'Unknown')}] - {meta.get('title', 'Bez tytułu')}"

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
    html, meta = build_mail_html()
    send_mail(html, meta)


if __name__ == "__main__":
    main()
