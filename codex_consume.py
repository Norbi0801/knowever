"""
Uruchamia Codex z promptem z pliku `prompt.md` w katalogu
`actual_process_feed/`.

Przepływ:
- sprawdza, czy istnieje `actual_process_feed/prompt.md`,
- czyta jego zawartość,
- uruchamia: `codex exec`, przekazując prompt przez stdin,
- pracuje z katalogu `actual_process_feed`, żeby Codex widział
  `article.json`, `content.html` i inne pliki obok.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROCESS_DIR = BASE_DIR / "actual_process_feed"
PROMPT_PATH = BASE_DIR / "prompt.md"


def main() -> None:
    if not PROCESS_DIR.exists():
        print(f"Brak katalogu {PROCESS_DIR} – nic do przetworzenia.")
        sys.exit(1)

    if not PROMPT_PATH.exists():
        print(f"Brak pliku {PROMPT_PATH} – utwórz prompt.md przed wywołaniem Codexa.")
        sys.exit(1)

    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    # --skip-git-repo-check, bo katalog może nie być zaufanym repo
    cmd = ["codex", "exec", "--skip-git-repo-check"]
    print(f"[codex_consume] Uruchamiam: {' '.join(cmd)} (cwd={PROCESS_DIR})")

    # Przekazujemy prompt przez stdin do Codexa
    result = subprocess.run(
        cmd,
        input=prompt,
        cwd=str(PROCESS_DIR),
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        print(f"[codex_consume] codex exec zakończył się kodem {result.returncode}")
        if result.stderr:
            print(result.stderr)
        sys.exit(result.returncode)

    # FS wewnątrz Codexa jest tylko do odczytu, ale my możemy
    # zapisać wynik jego stdout lokalnie.
    output_html = result.stdout
    if not output_html.strip():
        print("[codex_consume] Ostrzeżenie: brak danych na stdout Codexa – nic nie zapisuję.")
        return

    out_path = PROCESS_DIR / "output.html"
    out_path.write_text(output_html, encoding="utf-8")
    print(f"[codex_consume] Zapisano wynik Codexa do {out_path}")


if __name__ == "__main__":
    main()
