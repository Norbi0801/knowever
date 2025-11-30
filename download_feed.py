"""
Pobiera pełną zawartość HTML artykułu dla aktualnie
przetwarzanego wpisu (z `actual_process_feed/article.json`)
i zapisuje ją do `actual_process_feed/content.html`,
usuwając style i JavaScript.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin
from urllib.parse import urlparse
from datetime import datetime, timezone
import time
import os
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


BASE_DIR = Path(__file__).resolve().parent

dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


def get_process_dir() -> Path:
    pd = os.getenv("PROCESS_DIR")
    if pd:
        return Path(pd).resolve()
    return BASE_DIR / "actual_process_feed"


PROCESS_DIR = get_process_dir()
ARTICLE_PATH = PROCESS_DIR / "article.json"
CONTENT_PATH = PROCESS_DIR / "content.html"
FAIL_CACHE_PATH = BASE_DIR / "tmp" / "fetch_failures.json"
FAIL_TTL_SECONDS = 24 * 3600


def load_current_article() -> dict:
    if not ARTICLE_PATH.exists():
        raise FileNotFoundError(f"Brak pliku {ARTICLE_PATH} – nic do pobrania.")
    with ARTICLE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_html(url: str) -> str:
    """Pobiera HTML, a jeśli istnieje wersja AMP – próbuje użyć jej.

    Używamy nagłówka User-Agent, żeby zmniejszyć ryzyko 403 na niektórych serwisach.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Sprawdź cache błędów domeny
    parsed = urlparse(url)
    domain = parsed.netloc
    fail_cache = load_fail_cache()
    if domain in fail_cache:
        ts = fail_cache[domain]
        if time.time() - ts < FAIL_TTL_SECONDS:
            raise requests.RequestException(f"Pomijam {domain} – ostatnio błąd, cache TTL nie wygasł.")

    resp = requests.get(url, timeout=30, headers=headers)
    resp.raise_for_status()
    html = resp.text

    # Spróbuj znaleźć link rel="amphtml" i użyć prostszej wersji artykułu
    try:
        soup = BeautifulSoup(html, "html.parser")
        amp_link = soup.find("link", rel=lambda v: v and "amphtml" in v)
        if amp_link and amp_link.get("href"):
            amp_url = urljoin(url, amp_link["href"])
            amp_resp = requests.get(amp_url, timeout=30, headers=headers)
            amp_resp.raise_for_status()
            return amp_resp.text
    except Exception:
        # Jeśli coś pójdzie nie tak, zostajemy przy oryginalnym HTML
        pass

    return html


def strip_styles_and_scripts(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Usuń <script> i <style>
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Usuń atrybuty style z elementów
    for el in soup(True):
        if el.has_attr("style"):
            del el["style"]

    return str(soup)


def extract_main_content(html: str, title: str | None = None) -> str:
    """
    Próbuje wyłuskać główną treść artykułu z HTML w sposób ogólny:
    - szuka dużych fragmentów tekstu w <article>, <main>, <section>, <div>,
    - unika oczywistych nawigacji / footerów po klasach i rolach,
    - jako fallback używa całego <body>.

    Zwraca nowy, uproszczony dokument HTML z ewentualnym <h1> tytułem.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Najpierw spróbujmy znaleźć <article> – zwykle tam jest właściwa treść.
    candidates: list[tuple[int, BeautifulSoup]] = []
    for tag in soup.find_all("article"):
        text = tag.get_text(separator=" ", strip=True)
        length = len(text)
        if length < 400:
            continue

        role = (tag.get("role") or "").lower()
        cls = " ".join(tag.get("class") or []).lower()
        ident = (tag.get("id") or "").lower()
        bad_keywords = [
            "nav",
            "menu",
            "footer",
            "header",
            "subscribe",
            "comment",
            "share",
            "related",
            "cookie",
        ]
        if any(bad in role or bad in cls or bad in ident for bad in bad_keywords):
            continue

        candidates.append((length, tag))

    # Jeśli nie ma sensownych <article>, szukamy w szerszych tagach.
    if not candidates:
        for tag in soup.find_all(["main", "section", "div"]):
            text = tag.get_text(separator=" ", strip=True)
            length = len(text)
            if length < 400:
                continue

            role = (tag.get("role") or "").lower()
            cls = " ".join(tag.get("class") or []).lower()
            ident = (tag.get("id") or "").lower()
            bad_keywords = [
                "nav",
                "menu",
                "footer",
                "header",
                "subscribe",
                "comment",
                "share",
                "related",
                "cookie",
            ]
            if any(bad in role or bad in cls or bad in ident for bad in bad_keywords):
                continue

            candidates.append((length, tag))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        main_tag = candidates[0][1]
    else:
        # Fallback: cały <body> albo całość dokumentu
        main_tag = soup.body or soup

    # Wewnątrz wybranej sekcji usuń oczywiste nawigacje / stopki,
    # żeby zminimalizować śmieci wokół artykułu.
    for bad in main_tag.find_all(
        ["nav", "aside", "footer"],
    ):
        bad.decompose()
    for el in main_tag.find_all(True):
        if not isinstance(el, Tag):
            continue
        attrs = getattr(el, "attrs", {}) or {}
        role = str(attrs.get("role", "")).lower()
        classes = attrs.get("class", [])
        if isinstance(classes, str):
            cls = classes.lower()
        else:
            cls = " ".join(str(c) for c in classes).lower()
        ident = str(attrs.get("id", "")).lower()
        if any(k in role or k in cls or k in ident for k in ["nav", "menu", "footer", "header", "subscribe", "cookie"]):
            el.decompose()

    # Na koniec usuń wszystkie atrybuty z pozostałych tagów,
    # żeby HTML był jak najprostszy.
    for el in main_tag.find_all(True):
        if isinstance(el, Tag):
            el.attrs = {}

    # Zbuduj uproszczony dokument
    new_soup = BeautifulSoup("<html><head><meta charset='utf-8'></head><body></body></html>", "html.parser")
    body = new_soup.body

    if title:
        h1 = new_soup.new_tag("h1")
        h1.string = title
        body.append(h1)

    body.append(main_tag)

    return str(new_soup)


def main() -> None:
    article = load_current_article()
    url = article.get("url")
    if not url:
        print("Brak pola 'url' w article.json – pomijam.")
        return

    PROCESS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[download_feed] Pobieram HTML z: {url}")
    try:
        html = fetch_html(url)
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "?")
        print(f"[download_feed] HTTP error {status} dla URL: {url} – pomijam ten wpis.")
        remember_fail(url)
        return
    except requests.RequestException as exc:
        print(f"[download_feed] Błąd sieci podczas pobierania {url}: {exc} – pomijam ten wpis.")
        remember_fail(url)
        return
    cleaned = strip_styles_and_scripts(html)
    # Wyłuskaj główną treść, korzystając z tytułu jako nagłówka
    title = article.get("title")
    main_html = extract_main_content(cleaned, title=title)

    PROCESS_DIR.mkdir(parents=True, exist_ok=True)
    with CONTENT_PATH.open("w", encoding="utf-8") as f:
        f.write(main_html)

    print(f"[download_feed] Zapisano wyczyszczony HTML do {CONTENT_PATH}")


def load_fail_cache() -> dict:
    if not FAIL_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(FAIL_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_fail_cache(cache: dict) -> None:
    FAIL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAIL_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def remember_fail(url: str) -> None:
    parsed = urlparse(url)
    domain = parsed.netloc
    cache = load_fail_cache()
    cache[domain] = time.time()
    save_fail_cache(cache)


if __name__ == "__main__":
    main()
