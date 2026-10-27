#!/usr/bin/env python3
"""Step 3: import filled speaker sheets into data/gonja_pairs.jsonl.

Usage:
  python tools/import_csv.py sheets/*.csv --dry-run          # preview only
  python tools/import_csv.py sheets/ama.csv --consent        # really import
  python tools/import_csv.py kofi.csv --consent --default-contributor Kofi

--consent means: "every speaker in these files agreed that their translations
may be stored and used to train a translation model" (see SPEAKER_GUIDE.md).

Optional columns:
  ready   if the sheet has this column, only rows marked yes (y, true, 1, x) are imported.
          Fix a row first, mark it ready, then import: that way a wrong version never enters.
  source  where the pair came from (e.g. "Gonja Dictionary"); stored with the pair.
Imported pairs start as UNVERIFIED; a different speaker verifies them in step 4.
"""
import argparse
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import glossary  # noqa: E402


READY = {"yes", "y", "true", "1", "x", "ready"}


def read_rows(path):
    try:
        f = open(path, newline="", encoding="utf-8-sig")
        text = f.read()
        f.close()
    except UnicodeDecodeError:
        raise SystemExit(
            f"{path}: not UTF-8. In Excel use 'Save As > CSV UTF-8', otherwise "
            "special Gonja letters (like ɛ, ɔ) get damaged."
        )
    reader = csv.DictReader(text.splitlines())
    reader.fieldnames = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = {"english", "gonja"} - set(reader.fieldnames)
    if missing:
        raise SystemExit(f"{path}: missing column(s): {', '.join(sorted(missing))}")
    for line_no, row in enumerate(reader, start=2):
        yield line_no, {k: (v or "").strip() for k, v in row.items() if k and isinstance(v, (str, type(None)))}


def collect_files(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += sorted(os.path.join(p, n) for n in os.listdir(p) if n.lower().endswith(".csv"))
        else:
            files.append(p)
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_files", nargs="+", help="CSV files or folders of CSV files")
    ap.add_argument("--consent", action="store_true",
                    help="confirm every speaker consented to storage and training use")
    ap.add_argument("--default-contributor", help="used when the contributor column is empty")
    ap.add_argument("--dry-run", action="store_true", help="check the files, write nothing")
    ap.add_argument("--rejects", default="rejects.csv", help="where rejected rows are listed")
    args = ap.parse_args(argv)

    if not args.consent and not args.dry_run:
        raise SystemExit("Refusing to import without --consent (use --dry-run to preview).")

    existing = {(glossary._norm(r.get("en", "")), glossary._norm(r.get("gjn", ""))) for r in glossary._read()}
    summary = Counter()
    added_by = Counter()
    rejects = []

    for path in collect_files(args.csv_files):
        for line_no, row in read_rows(path):
            summary["rows"] += 1
            english, gonja = row.get("english", ""), row.get("gonja", "")
            source = row.get("source", "")
            contributor = row.get("contributor") or args.default_contributor or ""

            def reject(reason):
                summary["rejected"] += 1
                rejects.append([os.path.basename(path), line_no, reason, english, gonja, contributor])

            if "ready" in row and row["ready"].strip().lower() not in READY:
                summary["not_ready"] += 1
                continue
            if not gonja:
                summary["blank"] += 1
                continue
            if not english:
                reject("missing English sentence"); continue
            if not contributor:
                reject("missing contributor (fill the column or use --default-contributor)"); continue
            if "\ufffd" in gonja:
                reject("broken characters; save the sheet as CSV UTF-8"); continue
            if glossary._norm(gonja) == glossary._norm(english):
                reject("Gonja is identical to English (copy-paste?)"); continue
            if len(english) > glossary.MAX_LEN or len(gonja) > glossary.MAX_LEN:
                reject(f"longer than {glossary.MAX_LEN} characters"); continue

            key = (glossary._norm(english), glossary._norm(gonja))
            if key in existing:
                summary["duplicates"] += 1
                continue
            if not args.dry_run:
                result = glossary.add_pair(english, gonja, contributor, consent=True, source=source)
                if result["duplicate"]:
                    summary["duplicates"] += 1
                    continue
            existing.add(key)
            summary["added"] += 1
            added_by[contributor] += 1

    if rejects:
        with open(args.rejects, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["file", "line", "reason", "english", "gonja", "contributor"])
            w.writerows(rejects)

    mode = "DRY RUN (nothing written)" if args.dry_run else "IMPORTED"
    print(f"\n{mode}")
    print(f"  rows read:   {summary['rows']}")
    print(f"  {'would add' if args.dry_run else 'added':<12} {summary['added']}")
    print(f"  duplicates:  {summary['duplicates']}")
    print(f"  left blank:  {summary['blank']}")
    if summary["not_ready"]:
        print(f"  not ready:   {summary['not_ready']}  (the 'ready' column is not yes; they stay in your sheet)")
    print(f"  rejected:    {summary['rejected']}" + (f"  -> see {args.rejects}" if rejects else ""))
    for name, n in added_by.most_common():
        print(f"    {name}: {n}")
    if not args.dry_run and summary["added"]:
        print("\nNext (step 4): a different speaker verifies them via GET /pairs?verified=false")
    return {k: summary[k] for k in ("rows", "added", "duplicates", "blank", "rejected", "not_ready")}


if __name__ == "__main__":
    main()
