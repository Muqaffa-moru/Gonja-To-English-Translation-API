#!/usr/bin/env python3
"""Builds contribute/gonja-contribute.html from your prompt sheet.

  python tools/build_contribute_page.py gonja_prompts.csv
  python tools/build_contribute_page.py gonja_prompts.csv --endpoint https://script.google.com/macros/s/XXXX/exec

Sentences you already answered in the sheet get have=1, so the page shows
sentences nobody has answered first.
"""
import argparse
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def build(csv_path, endpoint=None, out=None):
    prompts = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("english"):
                continue
            prompts.append({"topic": row.get("topic") or "general",
                            "english": row["english"],
                            "have": 1 if row.get("gonja") else 0})
    with open(os.path.join(ROOT, "contribute", "template.html"), encoding="utf-8") as f:
        html = f.read()
    data = json.dumps(prompts, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("__PROMPTS_JSON__", data)
    if endpoint:
        html = html.replace("PASTE_YOUR_WEB_APP_URL_HERE", endpoint)
    out = out or os.path.join(ROOT, "contribute", "gonja-contribute.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out, len(prompts), sum(p["have"] for p in prompts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_file")
    ap.add_argument("--endpoint", help="your Apps Script web app address")
    ap.add_argument("--out")
    a = ap.parse_args()
    path, n, have = build(a.csv_file, a.endpoint, a.out)
    print(f"Wrote {path}: {n} sentences ({have} already answered, {n - have} still needed)")
