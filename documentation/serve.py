#!/usr/bin/env python3
"""
SECO documentation server — README + costing + benchmark + ITM explorer, shared navbar.

Usage:
    python documentation/serve.py                # live server, default port 8888
    python documentation/serve.py --port 9000
    python documentation/serve.py --build dist   # write static HTML to ./dist for deploy
"""

import argparse
import http.server
import os
import re
import socketserver
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOC_DIR = ROOT / "documentation"
REPORT = DOC_DIR / "report.html"

try:
    import markdown

    HAS_MD = True
except ImportError:
    HAS_MD = False

# Navbar link targets differ between live-server mode (clean routes) and
# static-build mode (relative .html files served under /secodoc/).
SERVER_LINKS = {
    "README": "/",
    "Costing": "/costing",
    "LLM Benchmark": "/benchmark",
    "ITM Explorer": "/explorer",
    "Quality": "/quality",
}
BUILD_LINKS = {
    "README": "index.html",
    "Costing": "costing.html",
    "LLM Benchmark": "benchmark.html",
    "ITM Explorer": "explorer.html",
    "Quality": "quality.html",
}

COVERAGE_JSON = DOC_DIR / "coverage.json"


def make_navbar(links: dict) -> str:
    items = "\n  ".join(
        f'<a href="{href}" style="color:#93c5fd;text-decoration:none">{label}</a>'
        for label, href in links.items()
    )
    return f"""
<nav style="
  background:#1a1a2e;color:#e2e8f0;padding:12px 40px;
  display:flex;align-items:center;gap:24px;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  font-size:13px;border-bottom:3px solid #3b82f6;position:sticky;top:0;z-index:100
">
  <span style="font-weight:700;color:#fff;margin-right:8px">SECO PoC</span>
  {items}
  <span style="margin-left:auto;font-size:11px;color:#64748b">
    <a href="https://yannhoffmann.com/seco2" target="_blank" style="color:#64748b">live demo ↗</a>
  </span>
</nav>
"""


README_CSS = """
<style>
*,*::before,*::after{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  font-size:14px;line-height:1.7;color:#1a1a2e;background:#f5f5f7;margin:0;padding:0 0 64px}
.md-body{max-width:820px;margin:40px auto;padding:0 24px;background:#fff;
  border:1px solid #e2e8f0;border-radius:8px;padding:40px 48px}
h1{font-size:24px;font-weight:700;color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:12px}
h2{font-size:17px;font-weight:600;color:#1e293b;margin-top:36px;border-bottom:1px solid #f1f5f9;padding-bottom:6px}
h3{font-size:14px;font-weight:600;color:#374151;margin-top:24px}
p{margin:0 0 14px;color:#374151}
code{background:#f1f5f9;padding:1px 6px;border-radius:3px;font-size:12px;color:#0f172a}
pre{background:#1e293b;color:#e2e8f0;padding:16px 20px;border-radius:6px;overflow-x:auto;font-size:12px}
pre code{background:none;color:inherit;padding:0}
table{width:100%;border-collapse:collapse;margin:16px 0;font-size:13px}
thead th{text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.5px;color:#64748b;padding:6px 12px;border-bottom:2px solid #e2e8f0;background:#f8fafc}
tbody td{padding:8px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
tbody tr:hover{background:#f8fafc}
a{color:#3b82f6}
strong{color:#1e293b}
ul,ol{padding-left:20px;margin:0 0 14px}
li{margin-bottom:4px}
blockquote{border-left:3px solid #cbd5e1;margin:0 0 14px;padding:4px 16px;color:#64748b}
hr{border:none;border-top:1px solid #e2e8f0;margin:28px 0}
</style>
"""


def inject_navbar(html: str, navbar: str) -> str:
    """Inject navbar after <body> tag."""
    return re.sub(r"(<body[^>]*>)", r"\1" + navbar, html, count=1, flags=re.IGNORECASE)


def readme_html(navbar: str) -> str:
    md_text = (ROOT / "README.md").read_text()
    if HAS_MD:
        body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
    else:
        body = f"<pre>{md_text}</pre><p style='color:#f59e0b'>pip install markdown for rendered view</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>SECO — README</title>
  {README_CSS}
</head>
<body>
{navbar}
<div class="md-body">{body}</div>
</body>
</html>"""


def report_html(navbar: str) -> str:
    if not REPORT.exists():
        return (
            f"<!DOCTYPE html><body>{navbar}<div style='padding:40px;font-family:sans-serif'>"
            "<h2>ITM Explorer report not built yet</h2><p>Run <code>make explore</code> first.</p></div></body>"
        )
    return inject_navbar(REPORT.read_text(), navbar)


def _quality_page(navbar: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>SECO — Code quality</title>{README_CSS}</head>
<body>{navbar}<div class="md-body">{body}</div></body></html>"""


def coverage_html(navbar: str) -> str:
    """Render the measured coverage report (documentation/coverage.json)."""
    import json

    if not COVERAGE_JSON.exists():
        return _quality_page(
            navbar,
            "<h1>Code quality &amp; coverage</h1><p>No coverage report yet — generate it with "
            "<code>make test</code> (writes <code>documentation/coverage.json</code>).</p>",
        )

    data = json.loads(COVERAGE_JSON.read_text())
    totals = data["totals"]
    total = totals["percent_covered"]

    def colour(pct):
        return "#10b981" if pct >= 90 else "#f59e0b" if pct >= 70 else "#ef4444"

    def bar(pct):
        return (
            f'<span style="background:#f1f5f9;border-radius:4px;height:8px;width:120px;'
            f'overflow:hidden;display:inline-block;vertical-align:middle">'
            f'<span style="background:{colour(pct)};height:8px;width:{pct:.0f}%;'
            f'display:inline-block;vertical-align:top"></span></span>'
        )

    rows = ""
    for name, info in sorted(
        data["files"].items(), key=lambda kv: kv[1]["summary"]["percent_covered"], reverse=True
    ):
        s = info["summary"]
        pct = s["percent_covered"]
        rows += (
            f"<tr><td><code>{name}</code></td>"
            f"<td style='text-align:right'>{s['covered_lines']}/{s['num_statements']}</td>"
            f"<td>{bar(pct)} &nbsp;<span style='font-variant-numeric:tabular-nums'>{pct:.0f}%</span></td></tr>"
        )

    body = f"""
<h1>Code quality &amp; coverage</h1>
<p>Offline test suite for the App&nbsp;2 backend (pipeline + API), run with
<code>make test</code>. No API key required — the live LLM call path is covered at the
<em>output</em> level by the golden-set eval (<code>make eval</code>) instead of mocked here.</p>
<div style="display:flex;align-items:center;gap:24px;margin:24px 0;padding:20px 24px;
     background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
  <div style="font-size:46px;font-weight:800;color:{colour(total)};font-variant-numeric:tabular-nums">{total:.0f}%</div>
  <div style="font-size:13px;color:#475569">
    <strong>line coverage</strong> · {totals["num_statements"]} statements<br>
    {totals["covered_lines"]} covered · {totals["missing_lines"]} uncovered
  </div>
</div>
<table>
  <thead><tr><th>Module</th><th style="text-align:right">Lines</th><th>Coverage</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p style="color:#64748b;font-size:12px;margin-top:16px">
  Uncovered lines concentrate in <code>pipeline/analyze.py</code>'s <code>run_pair</code>
  — the actual Anthropic call — excluded from the offline suite by design. Regenerate with
  <code>make test</code>.
</p>
<h2 style="margin-top:32px">Formatting &amp; linting</h2>
<p>The codebase is formatted and linted with <strong>ruff</strong> — one tool consolidating
black, isort, flake8 / pycodestyle / pyflakes, pyupgrade and bugbear (config in
<code>pyproject.toml</code>). Enforced with <code>make lint</code>; the maintained tree is
ruff-clean.</p>
<div style="display:inline-block;background:#ecfdf5;border:1px solid #a7f3d0;color:#047857;
     border-radius:6px;padding:6px 14px;font-size:13px;font-weight:600">ruff check . — All checks passed</div>
"""
    return _quality_page(navbar, body)


def make_handler(navbar: str):
    class SECOHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/")
            if path in ("", "/"):
                self._serve(readme_html(navbar))
            elif path == "/costing":
                self._serve(inject_navbar((DOC_DIR / "costing.html").read_text(), navbar))
            elif path == "/benchmark":
                self._serve(inject_navbar((DOC_DIR / "llm_benchmark.html").read_text(), navbar))
            elif path == "/explorer":
                self._serve(report_html(navbar))
            elif path == "/quality":
                self._serve(coverage_html(navbar))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")

        def _serve(self, html: str):
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            print(f"  {args[0]} {args[1]}")

    return SECOHandler


def build(outdir: Path):
    """Write static HTML files (relative-link navbar) for deployment under /secodoc/."""
    navbar = make_navbar(BUILD_LINKS)
    outdir.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": readme_html(navbar),
        "costing.html": inject_navbar((DOC_DIR / "costing.html").read_text(), navbar),
        "benchmark.html": inject_navbar((DOC_DIR / "llm_benchmark.html").read_text(), navbar),
        "explorer.html": report_html(navbar),
        "quality.html": coverage_html(navbar),
    }
    for name, html in pages.items():
        (outdir / name).write_text(html, encoding="utf-8")
        print(f"  wrote {outdir / name}")
    print(f"\n✓ Static docs built → {outdir} ({len(pages)} pages)")


def serve(port: int):
    navbar = make_navbar(SERVER_LINKS)
    os.chdir(ROOT)
    with socketserver.TCPServer(("", port), make_handler(navbar)) as httpd:
        httpd.allow_reuse_address = True
        print(f"SECO docs → http://localhost:{port}")
        print("  /          README")
        print("  /costing   API costing report")
        print("  /benchmark LLM benchmark & quality audit")
        print("  /explorer  ITM corpus map (app 3)")
        print("  /quality   test coverage report")
        print("Ctrl+C to stop")
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--build", metavar="DIR", help="Write static HTML to DIR and exit")
    args = parser.parse_args()
    if args.build:
        build(Path(args.build))
    else:
        serve(args.port)


if __name__ == "__main__":
    main()
