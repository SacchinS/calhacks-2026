"""The website Claude Code builds in the demo (claude_code_cli.project_dir in config.yaml).

    uv run python tools/demo_site.py reset   # fresh copy of demo/site (the old one is backed up)
    uv run python tools/demo_site.py serve   # http://localhost:8765, reloads when files change

`serve` adds a small reload script to each HTML page as it's served (the files on disk stay
as Claude Code wrote them). Open it in a browser next to the app.
"""

from __future__ import annotations

import argparse
import http.server
import json
import shutil
import sys
import time
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.config import ROOT, load_config  # noqa: E402

TEMPLATE = ROOT / "demo" / "site"
RELOAD = b"""<script>
(() => { let last = null;
  setInterval(async () => {
    try {
      const v = (await (await fetch("/__version", {cache: "no-store"})).json()).version;
      if (last !== null && v !== last) location.reload();
      last = v;
    } catch (e) {}
  }, 700);
})();
</script>"""


def project_dir() -> Path:
    return load_config().path("claude_code_cli.project_dir", "../demo-site").resolve()


def version(folder: Path) -> float:
    """Changes whenever any file in the site changes, appears, or disappears."""
    stamps = [p.stat().st_mtime for p in folder.rglob("*") if p.is_file() and ".git" not in p.parts]
    return round(sum(stamps) + len(stamps), 3)


def reset(folder: Path) -> None:
    if folder.exists():
        backup = folder.with_name(f"{folder.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}")
        folder.rename(backup)
        print(f"kept the old site as {backup}")
    shutil.copytree(TEMPLATE, folder)
    print(f"fresh demo site in {folder} (Claude Code starts a new session there)")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
        folder = Path(self.directory)
        if self.path == "/__version":
            return self._send(json.dumps({"version": version(folder)}).encode(), "application/json")
        path = self.path.split("?", 1)[0]
        file = folder / (path.lstrip("/") or "index.html")
        if file.is_dir():
            file = file / "index.html"
        if file.suffix == ".html" and file.is_file() and folder in file.resolve().parents:
            html = file.read_bytes()
            html = (
                html.replace(b"</body>", RELOAD + b"</body>")
                if b"</body>" in html
                else html + RELOAD
            )
            return self._send(html, "text/html; charset=utf-8")
        return super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def serve(folder: Path, port: int) -> None:
    if not folder.is_dir():
        sys.exit(f"{folder} doesn't exist yet: run `uv run python tools/demo_site.py reset` first")
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), partial(Handler, directory=str(folder))
    )
    print(f"serving {folder} at http://localhost:{port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", choices=["reset", "serve"])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    folder = project_dir()
    if args.command == "reset":
        reset(folder)
    else:
        serve(folder, args.port)


if __name__ == "__main__":
    main()
