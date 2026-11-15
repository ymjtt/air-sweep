"""Build index.html from src/index.template.html and the place statistics in prep/out/meta.json.
Run from anywhere: python3 src/build.py
Generated with Claude (Anthropic), an AI model, directed by the project author."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
template = open(os.path.join(HERE, "index.template.html"), encoding="utf-8").read()
meta = json.load(open(os.path.join(ROOT, "prep", "out", "meta.json"), encoding="utf-8"))
html = template.replace("/*META*/", json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(html)
print("wrote index.html,", len(html), "characters")
