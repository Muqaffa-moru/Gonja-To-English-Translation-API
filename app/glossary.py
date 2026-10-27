"""Gonja <-> English dataset + phrasebook (JSONL, one pair per line).

Each row:
  id, en, gjn, contributor, consent, verified, reviewer, created_at, verified_at,
  original_gjn (set when a reviewer corrected the Gonja), rejected, source (e.g. a dictionary the pair came from; null for pairs written by speakers)

Rules built into the data layer:
  * a pair is only saved with the contributor's consent
  * a DIFFERENT speaker must verify, correct or reject it (reviewer != contributor)
  * only verified pairs are used for translation lookups and training
    (set GONJA_REQUIRE_VERIFIED=false to test with unverified pairs)

This is NOT real machine translation: lookup is exact-phrase only. The value
is the dataset you are building for the model in the later steps."""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

PATH = os.getenv("GONJA_DATA", "data/gonja_pairs.jsonl")
REQUIRE_VERIFIED = os.getenv("GONJA_REQUIRE_VERIFIED", "true").lower() == "true"
MAX_LEN = 500
_lock = threading.RLock()


def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s']", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> list:
    if not os.path.exists(PATH):
        return []
    rows = []
    with open(PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write(rows: list) -> None:
    os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, PATH)


def add_pair(english: str, gonja: str, contributor: str = "anonymous", consent: bool = False, source: str = "") -> dict:
    english, gonja = english.strip(), gonja.strip()
    contributor = (contributor or "anonymous").strip() or "anonymous"
    if not consent:
        raise ValueError("The contributor must consent to their translation being stored and used for training.")
    if not english or not gonja:
        raise ValueError("Both English and Gonja text are required.")
    if len(english) > MAX_LEN or len(gonja) > MAX_LEN:
        raise ValueError(f"Each side must be at most {MAX_LEN} characters.")
    with _lock:
        for r in _read():
            if _norm(r.get("en", "")) == _norm(english) and _norm(r.get("gjn", "")) == _norm(gonja):
                return {"id": r.get("id"), "duplicate": True}
        row = {
            "id": uuid.uuid4().hex[:10], "en": english, "gjn": gonja,
            "contributor": contributor, "consent": True,
            "verified": False, "reviewer": None,
            "created_at": _now(), "verified_at": None,
            "original_gjn": None, "rejected": False,
            "source": (source or "").strip()[:80] or None,
        }
        os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
        with open(PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"id": row["id"], "duplicate": False}


def _review(pair_id: str, reviewer: str, change) -> dict:
    """Shared rules for verify / correct / reject."""
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ValueError("A reviewer name is required.")
    with _lock:
        rows = _read()
        for r in rows:
            if r.get("id") == pair_id:
                if reviewer.lower() == str(r.get("contributor", "")).strip().lower():
                    raise ValueError("A different speaker must review this pair.")
                if r.get("verified") or r.get("rejected"):
                    raise ValueError("This pair has already been reviewed.")
                change(r)
                r["reviewer"] = reviewer
                _write(rows)
                return r
    raise KeyError(pair_id)


def verify_pair(pair_id: str, reviewer: str) -> dict:
    return _review(pair_id, reviewer,
                   lambda r: r.update(verified=True, verified_at=_now()))


def correct_pair(pair_id: str, reviewer: str, gonja: str) -> dict:
    """Reviewer fixes the Gonja text; the original is kept for the record."""
    gonja = (gonja or "").strip()
    if not gonja:
        raise ValueError("The corrected Gonja text is required.")
    if len(gonja) > MAX_LEN:
        raise ValueError(f"Each side must be at most {MAX_LEN} characters.")

    def change(r):
        if _norm(gonja) == _norm(r.get("gjn", "")):
            raise ValueError("No change made; use verify instead.")
        r.update(original_gjn=r.get("gjn"), gjn=gonja, verified=True, verified_at=_now())

    return _review(pair_id, reviewer, change)


def reject_pair(pair_id: str, reviewer: str) -> dict:
    """Reviewer says the pair is wrong and not fixable. Excluded from everything."""
    return _review(pair_id, reviewer, lambda r: r.update(rejected=True, verified=False))


def list_pairs(verified=None, limit: int = 50, exclude_contributor: str = "") -> list:
    """Rejected pairs are never listed. exclude_contributor hides someone's own
    pairs (a reviewer never sees what they wrote)."""
    rows = [r for r in _read() if not r.get("rejected")]
    if verified is not None:
        rows = [r for r in rows if bool(r.get("verified")) == verified]
    ex = (exclude_contributor or "").strip().lower()
    if ex:
        rows = [r for r in rows if str(r.get("contributor", "")).strip().lower() != ex]
    return rows[: max(1, min(limit, 500))]


def stats() -> dict:
    rows = _read()
    rejected = [r for r in rows if r.get("rejected")]
    live = [r for r in rows if not r.get("rejected")]
    verified = [r for r in live if r.get("verified")]
    return {
        "total": len(rows),
        "verified": len(verified),
        "unverified": len(live) - len(verified),
        "rejected": len(rejected),
        "corrected": sum(1 for r in verified if r.get("original_gjn")),
        "contributors": len({r.get("contributor") for r in rows}),
        "reviewers": len({r.get("reviewer") for r in verified}),
    }


def lookup(text: str, direction: str):
    """direction: 'en->gjn' or 'gjn->en'. Newest matching entry wins."""
    src, tgt = ("en", "gjn") if direction == "en->gjn" else ("gjn", "en")
    key, found = _norm(text), None
    for r in _read():
        if r.get("rejected") or (REQUIRE_VERIFIED and not r.get("verified")):
            continue
        if _norm(r.get(src, "")) == key:
            found = r.get(tgt)
    return found
