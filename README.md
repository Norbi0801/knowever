# knowever – RSS → Codex → Mail (uv)

Minimalny projekt, który:

- czyta listę źródeł z `sources.yaml`,
- pobiera wpisy RSS do plików JSONL w `feeds/`,
- dla każdego nowego wpisu:
  - pobiera pełną stronę HTML artykułu,
  - przepuszcza ją przez Codexa z Twoim promptem,
  - zapisuje najlepsze wpisy do dziennego bufora z limitem liczby maili,
- raz dziennie składa jednego maila‑digest z top artykułami,
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

Plik `.env` w katalogu projektu określa ustawienia SMTP dla wysyłki maili przez `send_digest.py`.

Przykład:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=twoj_login_smtp
SMTP_PASS=twoje_haslo_smtp_lub_app_password
SMTP_FROM=Twoje Imię <twoj_email@example.com>
SMTP_TO=twoj_email_odbiorcy@example.com
MAX_POSTS_PER_DAY=10
SEND_MODE=digest          # albo individual (pojedyncze maile per wpis)
INCLUDE_AI_CONTENT=true   # false => tylko krótkie streszczenie/summary zamiast treści z Codexa
CLEAR_BUFFER_AFTER_SEND=true
FEED_DOWNLOAD_WORKERS=4   # równoległe pobieranie RSS
PROCESS_WORKERS=2         # równoległe przetwarzanie wpisów (oddzielne katalogi robocze)
SEND_WORKERS=3            # równoległa wysyłka w trybie individual
AUTO_SEND_DIGEST=false    # true => rss.py po przetwarzaniu od razu wyśle digest/maile
```

Uwagi:

- dla Gmaila użyj **hasła aplikacji** (App Password), nie zwykłego hasła konta,
- `SMTP_FROM` jest opcjonalne – jeśli puste, użyty zostanie `SMTP_USER`,
- `MAX_POSTS_PER_DAY` ogranicza liczbę artykułów (digest lub łączna liczba maili),
- `SEND_MODE`: `digest` wysyła jednego maila dziennie, `individual` – osobne maile dla wybranych wpisów,
- `INCLUDE_AI_CONTENT=false` sprawi, że w mailu będzie tylko krótkie summary/link (bez treści wygenerowanej przez AI),
- `CLEAR_BUFFER_AFTER_SEND` czyści dzisiejsze wpisy po wysyłce, by nie duplikować.
- `FEED_DOWNLOAD_WORKERS` – ile wątków do pobierania RSS,
- `PROCESS_WORKERS` – ile równoległych jobów przetwarzania (każdy ma własny katalog `actual_process_feed/job_*`),
- `SEND_WORKERS` – ile równoległych wątków wysyłki w trybie `individual`.
- `AUTO_SEND_DIGEST=true` – po `uv run rss.py` automatycznie uruchomi `send_digest.py`.

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
     - liczy score według `profile.yaml` (świeżość, punkty, słowa‑klucze),
     - respektuje limity: globalny `MAX_POSTS_PER_DAY` oraz `max_per_source`,
     - jeśli wpis przeszedł progi, uruchamia `process_feed.py`.

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
     - jeśli `INCLUDE_AI_CONTENT=false`, krok Codexa jest pomijany, a do bufora trafia krótkie summary.

   - zapis do bufora
     - łączy dane wpisu + `output.html` + score i dopisuje linię do `daily_buffer.jsonl`
       (tylko jeśli przeszedł progi).

   - na końcu czyści zawartość katalogu `actual_process_feed/`.

3. `send_digest.py`
   - zbiera dzisiejsze wpisy z `daily_buffer.jsonl`,
   - sortuje po score, tnie do limitu `MAX_POSTS_PER_DAY`,
   - tryb `digest`: buduje jednego maila z listą wpisów,
   - tryb `individual`: wysyła osobne maile dla każdego wpisu,
   - `INCLUDE_AI_CONTENT=false` – w treści pojawi się tylko summary/link (bez AI, Codex pomijany).

Do regularnego działania:
- uruchamiaj `uv run rss.py` kilka razy dziennie (lub w cronie) aby zapełnić bufor,
- uruchom `uv run send_digest.py` raz dziennie o godzinie z `profile.yaml` (np. Task Scheduler / cron).
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
- konfiguracja scoringu/limitów: `profile.yaml` + `MAX_POSTS_PER_DAY` w `.env`
- pobranie + selekcja: `uv run rss.py`
- wysyłka dziennego maila: `uv run send_digest.py`
- tylko pobranie feedów: `uv run rss_download.py`
- debug pojedynczego wpisu:
  - skopiuj wpis do `actual_process_feed/article.json`,
  - przygotuj `prompt.md`,
  - uruchom `uv run process_feed.py`
- dane surowe: `feeds/*.jsonl`
- bufor do digestu: `daily_buffer.jsonl`
