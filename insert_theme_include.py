from pathlib import Path

templates_dir = Path(__file__).resolve().parent / "app" / "templates"
snippet = "    {% include 'partials/theme_head.html' %}\n"
marker = "</title>"

for template in sorted(templates_dir.glob("*.html")):
    text = template.read_text(encoding="utf-8")
    if "partials/theme_head.html" in text:
        continue
    idx = text.find(marker)
    if idx == -1:
        continue
    idx += len(marker)
    text = text[:idx] + "\n" + snippet + text[idx:]
    template.write_text(text, encoding="utf-8")

