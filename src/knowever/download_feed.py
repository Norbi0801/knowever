from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Dict, Tuple

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from .config import Config
from .paths import Paths


def _load_fail_cache(fail_cache_path: Path) -> dict:
    if not fail_cache_path.exists():
        return {}
    try:
        return json.loads(fail_cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_fail_cache(cache: dict, fail_cache_path: Path) -> None:
    fail_cache_path.parent.mkdir(parents=True, exist_ok=True)
    fail_cache_path.write_text(json.dumps(cache), encoding="utf-8")


def remember_fail(url: str, paths: Paths) -> None:
    parsed = urlparse(url)
    domain = parsed.netloc
    cache = _load_fail_cache(paths.fail_cache)
    cache[domain] = time.time()
    _save_fail_cache(cache, paths.fail_cache)


def fetch_html(url: str, paths: Paths, cfg: Config) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    parsed = urlparse(url)
    domain = parsed.netloc
    fail_cache = _load_fail_cache(paths.fail_cache)
    if domain in fail_cache:
        ts = fail_cache[domain]
        if time.time() - ts < cfg.fail_ttl_seconds:
            raise requests.RequestException(
                f"Skipping {domain} - last attempt failed and fail TTL has not expired."
            )

    resp = requests.get(url, timeout=30, headers=headers)
    resp.raise_for_status()
    html = resp.text

    try:
        soup = BeautifulSoup(html, "html.parser")
        amp_link = soup.find("link", rel=lambda v: v and "amphtml" in v)
        if amp_link and amp_link.get("href"):
            amp_url = urljoin(url, amp_link["href"])
            amp_resp = requests.get(amp_url, timeout=30, headers=headers)
            amp_resp.raise_for_status()
            return amp_resp.text
    except Exception:
        pass

    return html


def strip_styles_and_scripts(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for el in soup(True):
        if el.has_attr("style"):
            del el["style"]
    return str(soup)


def extract_main_content(html: str, title: str | None = None) -> str:
    soup = BeautifulSoup(html, "html.parser")

    candidates = []
    for tag in soup.find_all("article"):
        text = tag.get_text(separator=" ", strip=True)
        length = len(text)
        if length < 400:
            continue
        role = (tag.get("role") or "").lower()
        cls = " ".join(tag.get("class") or []).lower()
        ident = (tag.get("id") or "").lower()
        bad_keywords = ["nav", "menu", "footer", "header", "subscribe", "comment", "share", "related", "cookie"]
        if any(bad in role or bad in cls or bad in ident for bad in bad_keywords):
            continue
        candidates.append((length, tag))

    if not candidates:
        for tag in soup.find_all(["main", "section", "div"]):
            text = tag.get_text(separator=" ", strip=True)
            length = len(text)
            if length < 400:
                continue
            role = (tag.get("role") or "").lower()
            cls = " ".join(tag.get("class") or []).lower()
            ident = (tag.get("id") or "").lower()
            bad_keywords = ["nav", "menu", "footer", "header", "subscribe", "comment", "share", "related", "cookie"]
            if any(bad in role or bad in cls or bad in ident for bad in bad_keywords):
                continue
            candidates.append((length, tag))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        main_tag = candidates[0][1]
    else:
        main_tag = soup.body or soup

    for bad in main_tag.find_all(["nav", "aside", "footer"]):
        bad.decompose()
    for el in main_tag.find_all(True):
        if not isinstance(el, Tag):
            continue
        attrs = getattr(el, "attrs", {}) or {}
        role = str(attrs.get("role", "")).lower()
        classes = attrs.get("class", [])
        cls = " ".join(str(c) for c in classes).lower()
        ident = str(attrs.get("id", "")).lower()
        if any(k in role or k in cls or k in ident for k in ["nav", "menu", "footer", "header", "subscribe", "cookie"]):
            el.decompose()

    for el in main_tag.find_all(True):
        if isinstance(el, Tag):
            el.attrs = {}

    new_soup = BeautifulSoup("<html><head><meta charset='utf-8'></head><body></body></html>", "html.parser")
    body = new_soup.body
    if title:
        h1 = new_soup.new_tag("h1")
        h1.string = title
        body.append(h1)
    body.append(main_tag)

    return str(new_soup)


def download_article(article: dict, process_dir: Path, paths: Paths, cfg: Config) -> Path:
    """Fetch HTML and save content.html inside process_dir."""
    url = article.get("url")
    if not url:
        raise ValueError("Missing 'url' field in article.json - skipping.")

    process_dir.mkdir(parents=True, exist_ok=True)

    html = fetch_html(url, paths, cfg)
    cleaned = strip_styles_and_scripts(html)
    title = article.get("title")
    main_html = extract_main_content(cleaned, title=title)

    content_path = process_dir / "content.html"
    content_path.write_text(main_html, encoding="utf-8")
    return content_path
