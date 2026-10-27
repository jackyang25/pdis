"""Generate `.env.example` from the settings table in `shared/settings.py`.

The table is the authority: names, defaults, which entries are credentials, and what each
does. Run this after changing it; a test asserts the committed file matches.

    .venv/bin/python scripts/generate_env_example.py
"""

from __future__ import annotations

from pathlib import Path

from shared.settings import render_example

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def main() -> None:
    EXAMPLE.write_text(render_example())


if __name__ == "__main__":
    main()
