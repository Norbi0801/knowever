# knowever – RSS → Codex → Mail (uv)

Minimalny projekt, który:

- czyta listę źródeł z `sources.yaml`,
- pobiera wpisy RSS do plików JSONL w `feeds/`,
- dla każdego nowego wpisu:
  - pobiera pełną stronę HTML artykułu,
  - przepuszcza ją przez Codexa z Twoim promptem,
  - składa z tego ostylowanego maila HTML,
  - wysyła mail na Twoje konto,
- nie duplikuje wpisów (sprawdza ID każdego wpisu + historię przetworzonych).

Całość jest zarządzana przez `uv`.

---

## Wymagania

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) zainstalowany w systemie

Instalacja `uv` (przykład, Linux/macOS):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Na Windows/WSL – patrz instrukcja w repo `uv`.

---

## Instalacja zależności (uv)

W katalogu projektu (`knowever/`):

```bash
uv sync
```

To:

- utworzy wirtualne środowisko,
- zainstaluje zależności z `pyproject.toml`
  (`feedparser`, `PyYAML`, `requests`, `beautifulsoup4`, `python-dotenv`).

---

## Konfiguracja SMTP (.env)

Plik `.env` w katalogu projektu określa ustawienia SMTP dla wysyłki maili przez `build_mail.py`.

Przykład:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=twoj_login_smtp
SMTP_PASS=twoje_haslo_smtp_lub_app_password
SMTP_FROM=Twoje Imię <twoj_email@example.com>
```

Uwagi:

- dla Gmaila użyj **hasła aplikacji** (App Password), nie zwykłego hasła konta,
- `SMTP_FROM` jest opcjonalne – jeśli puste, użyty zostanie `SMTP_USER`.

---

## Konfiguracja źródeł RSS

Plik: `sources.yaml`

Przykład:

```yaml
- name: Hacker News Frontpage
  url: https://hnrss.org/frontpage

- name: Dev.to Top
  url: https://dev.to/feed
```

Możesz:

- usuwać istniejące źródła,
- dodawać nowe (`name` jest tylko etykietą do nazwy pliku, `url` to adres RSS).

---

## Pipeline: RSS → Codex → Mail

Główny entrypoint:

```bash
uv run rss.py
```

Co się wtedy dzieje:

1. `rss.py`
   - uruchamia `rss_download.py`:
     - wczytuje `sources.yaml`,
     - dla każdego źródła tworzy / uzupełnia:
       - `feeds/<slug>.jsonl` (np. `feeds/hacker_news_frontpage.jsonl`),
     - dopisuje tylko nowe wpisy (sprawdza po polu `id`).
   - uruchamia `rss_process.py`:
     - przechodzi po wszystkich plikach `feeds/*.jsonl` w trybie round‑robin
       (1. wpis z pierwszego feedu, 1. z drugiego, 1. z trzeciego, potem 2. z pierwszego itd.),
     - dla każdego wpisu o nowym `id`:
       - kopiuje go do `actual_process_feed/article.json`,
       - uruchamia `process_feed.py`.

2. `process_feed.py` (dla jednego wpisu):

   - `download_feed.py`
     - czyta `actual_process_feed/article.json`,
     - pobiera pełną stronę HTML `url` (stara się użyć wersji AMP, jeśli istnieje),
     - usuwa skrypty, style, atrybuty i wycina główną treść artykułu,
     - zapisuje `actual_process_feed/content.html`.

   - `codex_consume.py`
     - czyta `actual_process_feed/prompt.md`,
     - uruchamia `codex exec --skip-git-repo-check` z `cwd=actual_process_feed`,
     - przekazuje prompt przez stdin,
     - zapisuje stdout Codexa do `actual_process_feed/output.html`.

   - `build_mail.py`
     - czyta:
       - `actual_process_feed/article.json`,
       - `actual_process_feed/output.html`,
       - szablon `email_template.html`,
     - wypełnia szablon:
       - `{{title}}`, `{{time}}`, `{{source}}`, `{{url}}`, `{{summary}}`, `{{content_html}}`,
     - wysyła mail HTML na `norbertolkowski@gmail.com` przez SMTP
       (temat: `[NEWSFEED] [SOURCE] - title`).

   - na końcu czyści zawartość katalogu `actual_process_feed/`.

---

## Format danych w `feeds/`

Każdy plik w `feeds/*.jsonl` to JSONL (po jednym wpisie na linię).

Struktura przykładowego wpisu:

```json
{
  "id": "unikalny_id_wpisu",
  "source": "Hacker News Frontpage",
  "title": "Tytuł artykułu",
  "url": "https://...",
  "published": "2025-11-29T09:30:00",
  "summary": "Krótki opis",
  "content": "Pełniejsza treść / zawartość wpisu"
}
```

Możesz potem:

- budować własne analizy na plikach `feeds/*.jsonl`,
- ręcznie testować pipeline na pojedynczych wpisach (kopiując obiekt do `article.json`).

---

## Szybki cheat sheet

- instalacja zależności: `uv sync`
- konfiguracja feedów: edytuj `sources.yaml`
- konfiguracja SMTP: uzupełnij `.env`
- pełny pipeline (RSS → Codex → mail):
  - `uv run rss.py`
- tylko pobranie / aktualizacja feedów:
  - `uv run rss_download.py`
- debug pojedynczego wpisu:
  - skopiuj wpis do `actual_process_feed/article.json`,
  - przygotuj `actual_process_feed/prompt.md`,
  - uruchom `uv run process_feed.py`
- dane surowe: `feeds/*.jsonl`
