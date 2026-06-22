#!/usr/bin/env python3
"""
SECO documentation server — serves README + costing + benchmark with a shared navbar.

Usage:
    python documentation/serve.py          # default port 8888
    python documentation/serve.py --port 9000
"""
import argparse
import http.server
import os
import re
import socketserver
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOC_DIR = ROOT / "documentation"

try:
    import markdown
    HAS_MD = True
except ImportError:
    HAS_MD = False

NAVBAR = """
<nav style="
  background:#1a1a2e;color:#e2e8f0;padding:12px 40px;
  display:flex;align-items:center;gap:24px;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  font-size:13px;border-bottom:3px solid #3b82f6;position:sticky;top:0;z-index:100
">
  <span style="font-weight:700;color:#fff;margin-right:8px">SECO PoC</span>
  <a href="/" style="color:#93c5fd;text-decoration:none">README</a>
  <a href="/costing" style="color:#93c5fd;text-decoration:none">Costing</a>
  <a href="/benchmark" style="color:#93c5fd;text-decoration:none">LLM Benchmark</a>
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

def inject_navbar(html: str) -> str:
    """Inject navbar after <body> tag."""
    return re.sub(r'(<body[^>]*>)', r'\1' + NAVBAR, html, count=1, flags=re.IGNORECASE)


def readme_html() -> str:
    md_text = (ROOT / "README.md").read_text()
    if HAS_MD:
        body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    else:
        # Fallback: wrap in <pre> if markdown not installed
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
{NAVBAR}
<div class="md-body">{body}</div>
</body>
</html>"""


class SECOHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        if path in ("", "/"):
            self._serve_html(readme_html())
        elif path == "/costing":
            html = (DOC_DIR / "costing.html").read_text()
            self._serve_html(inject_navbar(html))
        elif path == "/benchmark":
            html = (DOC_DIR / "llm_benchmark.html").read_text()
            self._serve_html(inject_navbar(html))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def _serve_html(self, html: str):
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"  {args[0]} {args[1]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()

    os.chdir(ROOT)
    with socketserver.TCPServer(("", args.port), SECOHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"SECO docs → http://localhost:{args.port}")
        print("  /          README")
        print("  /costing   API costing report")
        print("  /benchmark LLM benchmark & quality audit")
        print("Ctrl+C to stop")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
