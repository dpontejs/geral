"""Download the jogo da velha player base into `src/geral/games/velha/base.json`.

Run with `uv run python scripts/import_base.py`, read the report (players per club, Seleção, Copa),
review the diff of the generated file, then commit it. The board clubs are in
`src/geral/games/velha/clubes.toml`. Answers are kept in `~/.cache/geral/velha-http/` so a run
that failed midway (or a change to the grouping) resumes without asking again; `--fresh` clears it.
"""

import hashlib
import shutil
import sys
from pathlib import Path

import httpx

from geral.games.mediawiki import HEADERS
from geral.games.velha.base import BASE, load_clubs
from geral.games.velha.importacao import build_base, dump

CACHE = Path.home() / ".cache" / "geral" / "velha-http"


class CachedTransport(httpx.HTTPTransport):
    """Keeps every successful answer on disk, by URL."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = CACHE / hashlib.sha256(str(request.url).encode()).hexdigest()
        if path.exists():
            return httpx.Response(200, content=path.read_bytes(), request=request)
        response = super().handle_request(request)
        if response.status_code == 200:
            response.read()
            path.write_bytes(response.content)
        return response


def main() -> None:
    if "--fresh" in sys.argv:
        shutil.rmtree(CACHE, ignore_errors=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    transport = CachedTransport()
    with httpx.Client(headers=HEADERS, timeout=120, transport=transport) as client:
        data, report = build_base(client, load_clubs())
    BASE.write_text(dump(data), encoding="utf-8")
    print(f"wrote {BASE}")
    print("\n".join(report))


if __name__ == "__main__":
    main()
