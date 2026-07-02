#!/usr/bin/env python3
"""Render essential_docs/system-architecture.md to a diagrammed PDF.

Loads the Markdown, renders it client-side with marked.js + mermaid@11 (drawn UML,
not raw text), then uses Playwright Chromium `page.pdf()` to produce
essential_docs/system-architecture.pdf. Fully automated; needs network (jsdelivr CDN)
and the Playwright Chromium browser (already installed).

    python scripts/build-architecture-pdf.py
"""
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
MD = REPO / "essential_docs" / "system-architecture.md"
PDF = REPO / "essential_docs" / "system-architecture.pdf"

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Loop — System Architecture</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  :root { --ink:#0E1116; --muted:#5b6675; --line:#e2e7ee; --accent:#3DD9B0; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Inter, Arial, sans-serif; color: var(--ink);
         margin: 0; padding: 0 44px 44px; line-height: 1.55; font-size: 13.5px; }
  .cover { padding: 90px 0 40px; border-bottom: 3px solid var(--accent); margin-bottom: 34px;
           page-break-after: always; }
  .cover h1 { font-size: 46px; margin: 0 0 10px; letter-spacing: -1px; }
  .cover .sub { font-size: 18px; color: var(--muted); max-width: 640px; }
  .cover .meta { margin-top: 40px; font-family: "JetBrains Mono", Consolas, monospace;
                 font-size: 12px; color: var(--muted); }
  h1,h2,h3 { line-height: 1.25; }
  h1 { font-size: 26px; margin: 30px 0 12px; }
  h2 { font-size: 20px; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--line);
       page-break-before: always; }
  h2:first-of-type { page-break-before: avoid; }
  h3 { font-size: 15px; margin: 18px 0 8px; }
  p, li { color: #222831; }
  code { font-family: "JetBrains Mono", Consolas, monospace; font-size: 12px;
         background: #f3f5f8; padding: 1px 5px; border-radius: 4px; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12px; }
  th, td { border: 1px solid var(--line); padding: 6px 9px; text-align: left; vertical-align: top; }
  th { background: #f3f5f8; }
  a { color: #0a7f6b; text-decoration: none; }
  .mermaid { margin: 14px 0 22px; text-align: center; page-break-inside: avoid; }
  .mermaid svg { max-width: 100%; height: auto; }
  hr { border: none; border-top: 1px solid var(--line); margin: 22px 0; }
</style>
</head>
<body>
  <div class="cover">
    <h1>Loop</h1>
    <div class="sub">System Architecture &amp; Workflow — the AI Meeting-to-Execution Operator on the Lemma platform.</div>
    <div class="meta">Reference document · UML: component · ER · workflow · sequence · state · memory data-flow</div>
  </div>
  <div id="content"></div>
<script>
  const MD = __MD_JSON__;
  const renderer = new marked.Renderer();
  const origCode = renderer.code.bind(renderer);
  renderer.code = function(code, lang) {
    const text = (typeof code === 'object' && code !== null) ? code.text : code;
    const language = (typeof code === 'object' && code !== null) ? code.lang : lang;
    if ((language || '').trim() === 'mermaid') {
      return '<div class="mermaid">' + text + '</div>';
    }
    return origCode(code, lang);
  };
  marked.setOptions({ renderer });
  document.getElementById('content').innerHTML = marked.parse(MD);
  mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose',
                       flowchart: { htmlLabels: true, useMaxWidth: true } });
  (async () => {
    try {
      await mermaid.run({ querySelector: '.mermaid' });
    } catch (e) {
      window.__MERMAID_ERR__ = String(e);
    }
    window.__READY__ = true;
  })();
</script>
</body>
</html>
"""


def main() -> int:
    if not MD.exists():
        print(f"ERROR: {MD} not found", file=sys.stderr)
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed (pip install playwright)", file=sys.stderr)
        return 1

    md_text = MD.read_text(encoding="utf-8")
    html = HTML_TEMPLATE.replace("__MD_JSON__", json.dumps(md_text))

    tmp_html = REPO / "essential_docs" / "_arch_tmp.html"
    tmp_html.write_text(html, encoding="utf-8")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(tmp_html.as_uri(), wait_until="networkidle")
            page.wait_for_function("window.__READY__ === true", timeout=60000)
            err = page.evaluate("window.__MERMAID_ERR__ || null")
            if err:
                print(f"WARNING: mermaid reported: {err}", file=sys.stderr)
            # Give fonts/SVG a beat to settle before printing.
            page.wait_for_timeout(800)
            page.pdf(
                path=str(PDF),
                format="A4",
                print_background=True,
                margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
            )
            browser.close()
    finally:
        tmp_html.unlink(missing_ok=True)

    size = PDF.stat().st_size if PDF.exists() else 0
    if size < 5000:
        print(f"ERROR: PDF too small ({size} bytes) — render likely failed", file=sys.stderr)
        return 1
    print(f"OK: wrote {PDF} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
