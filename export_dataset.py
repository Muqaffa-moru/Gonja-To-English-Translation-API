#!/usr/bin/env python3
"""Step 5: clean the verified pairs and split them into train / validation / test.

Usage:
  python tools/export_dataset.py                      # writes ./export/
  python tools/export_dataset.py --out my_export --test 0.1 --val 0.1
  python tools/export_dataset.py --include-unverified # DEMO ONLY: never train on this

What it does
  1. keeps only VERIFIED, non-rejected pairs
  2. cleans text (Unicode NFC, tidy spaces) and drops broken rows (see dropped.csv)
  3. splits by ENGLISH SENTENCE using a hash, so
       - all Gonja variants of one sentence stay in the same split
       - a pair never moves between splits when you add more data later,
         so your test set stays fixed and scores stay comparable over time
  4. removes train/validation pairs whose Gonja text also appears in a "later"
     split (test beats validation beats train) so nothing leaks into the test set
Output: train.jsonl, validation.jsonl, test.jsonl, dropped.csv, stats.json
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import glossary  # noqa: E402

MIN_PAIRS = 20          # refuse below this (nothing meaningful to split)
MAX_LEN_RATIO = 8.0     # chars; larger = probably misaligned


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def bucket(key: str, seed: str) -> float:
    h = hashlib.sha256(f"{seed}|{key}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def problem(en: str, gj: str):
    if not en or not gj:
        return "empty text"
    both = en + gj
    if "\ufffd" in both or any(unicodedata.category(c) == "Cc" for c in both):
        return "broken or control characters"
    if glossary._norm(en) == glossary._norm(gj):
        return "Gonja identical to English"
    ratio = max(len(en), len(gj)) / max(1, min(len(en), len(gj)))
    if ratio > MAX_LEN_RATIO:
        return f"length ratio {ratio:.1f}x (misaligned?)"
    return None


def build(rows, test_frac=0.10, val_frac=0.10, seed="gonja-v1", include_unverified=False, exclude_sources=()):
    kept, dropped, seen = [], [], set()
    for r in rows:
        if r.get("rejected"):
            continue
        if not include_unverified and not r.get("verified"):
            continue
        en, gj = clean(r.get("en")), clean(r.get("gjn"))
        if r.get("source") and r["source"] in exclude_sources:
            continue                                   # e.g. a source you lack permission to train on
        pid = r.get("id") or hashlib.sha1(f"{en}|{gj}".encode()).hexdigest()[:10]
        why = problem(en, gj)
        key = (glossary._norm(en), glossary._norm(gj))
        if not why and key in seen:
            why = "duplicate pair"
        if why:
            dropped.append({"id": pid, "reason": why, "en": en, "gjn": gj})
            continue
        seen.add(key)
        kept.append({"id": pid, "en": en, "gjn": gj,
                     "_en_key": key[0], "_gj_key": key[1],
                     "_corrected": bool(r.get("original_gjn")),
                     "_by": r.get("contributor"), "_rev": r.get("reviewer"),
                     "_src": r.get("source") or "speakers"})

    splits = {"train": [], "validation": [], "test": []}
    for p in kept:
        x = bucket(p["_en_key"], seed)
        name = "test" if x < test_frac else "validation" if x < test_frac + val_frac else "train"
        splits[name].append(p)

    # leak removal: same Gonja text must not appear across splits (test > validation > train)
    test_gj = {p["_gj_key"] for p in splits["test"]}
    kept_val = []
    for p in splits["validation"]:
        if p["_gj_key"] in test_gj:
            dropped.append({"id": p["id"], "reason": "same Gonja text appears in test", "en": p["en"], "gjn": p["gjn"]})
        else:
            kept_val.append(p)
    splits["validation"] = kept_val
    later = test_gj | {p["_gj_key"] for p in kept_val}
    kept_train = []
    for p in splits["train"]:
        if p["_gj_key"] in later:
            dropped.append({"id": p["id"], "reason": "same Gonja text appears in validation/test", "en": p["en"], "gjn": p["gjn"]})
        else:
            kept_train.append(p)
    splits["train"] = kept_train

    for name in splits:
        splits[name].sort(key=lambda p: (p["_en_key"], p["id"]))
    return splits, dropped


def write_outputs(out, splits, dropped, include_unverified):
    os.makedirs(out, exist_ok=True)
    for name, items in splits.items():
        with open(os.path.join(out, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for p in items:
                f.write(json.dumps({"id": p["id"], "en": p["en"], "gjn": p["gjn"]}, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "dropped.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "reason", "english", "gonja"])
        for d in dropped:
            w.writerow([d["id"], d["reason"], d["en"], d["gjn"]])
    allp = [p for items in splits.values() for p in items]
    stats = {
        "unverified_included": include_unverified,
        "pairs": {k: len(v) for k, v in splits.items()},
        "total_pairs": len(allp),
        "unique_english": len({p["_en_key"] for p in allp}),
        "dropped": len(dropped),
        "corrected_by_reviewer": sum(p["_corrected"] for p in allp),
        "by_source": dict(Counter(p["_src"] for p in allp)),
        "contributors": len({p["_by"] for p in allp}),
        "reviewers": len({p["_rev"] for p in allp if p["_rev"]}),
        "avg_chars_en": round(sum(len(p["en"]) for p in allp) / max(1, len(allp)), 1),
        "avg_chars_gjn": round(sum(len(p["gjn"]) for p in allp) / max(1, len(allp)), 1),
        "dropped_reasons": dict(Counter(d["reason"] for d in dropped)),
    }
    with open(os.path.join(out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="export")
    ap.add_argument("--test", type=float, default=0.10, help="fraction for the test set (default 0.10)")
    ap.add_argument("--val", type=float, default=0.10, help="fraction for validation (default 0.10)")
    ap.add_argument("--seed", default="gonja-v1", help="keep the same seed forever so the test set never changes")
    ap.add_argument("--exclude-source", action="append", default=[], metavar="NAME",
                    help='leave out pairs from this source, e.g. --exclude-source "Gonja Dictionary" (repeatable)')
    ap.add_argument("--include-unverified", action="store_true", help="DEMO ONLY: includes unverified pairs")
    ap.add_argument("--dry-run", action="store_true", help="show counts, write nothing")
    ap.add_argument("--allow-small", action="store_true", help=f"allow fewer than {MIN_PAIRS} pairs")
    args = ap.parse_args(argv)
    if not (0 < args.test < 0.5 and 0 < args.val < 0.5 and args.test + args.val < 0.6):
        raise SystemExit("--test and --val must each be between 0 and 0.5 (and sum below 0.6).")

    splits, dropped = build(glossary._read(), args.test, args.val, args.seed, args.include_unverified, tuple(args.exclude_source))
    total = sum(len(v) for v in splits.values())
    if total < MIN_PAIRS and not args.allow_small:
        raise SystemExit(f"Only {total} usable pairs (need {MIN_PAIRS}+). Get more pairs verified first, "
                         "or use --allow-small / --include-unverified to look at the format.")

    if args.dry_run:
        stats = {"pairs": {k: len(v) for k, v in splits.items()}, "dropped": len(dropped)}
    else:
        stats = write_outputs(args.out, splits, dropped, args.include_unverified)

    p = stats["pairs"]
    print(("\nDRY RUN, nothing written" if args.dry_run else f"\nWritten to {args.out}/") +
          f"\n  train:      {p['train']}\n  validation: {p['validation']}\n  test:       {p['test']}\n  dropped:    {stats['dropped']}")
    if stats.get("by_source") and len(stats["by_source"]) > 1:
        print("  by source:  " + ", ".join(f"{k} {v}" for k, v in stats["by_source"].items()))
    if args.include_unverified:
        print("\n  !! UNVERIFIED pairs included: use for a format demo only, never for real training.")
    if p["test"] < 30:
        print(f"\n  Warning: the test set has only {p['test']} pairs, so scores will be noisy. Keep collecting.")
    if total < 500:
        print(f"  Note: {total} pairs is below ~500, which only supports a rough first experiment.")
    return stats


if __name__ == "__main__":
    main()
