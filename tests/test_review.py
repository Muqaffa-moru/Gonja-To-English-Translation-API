import os, sys, tempfile
os.environ["GONJA_DATA"] = os.path.join(tempfile.mkdtemp(), "pairs.jsonl")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import glossary as g

ids = {}
for en, gj in [("one", "G1"), ("two", "G2"), ("three", "G3"), ("four", "G4")]:
    ids[en] = g.add_pair(en, gj, "Ama", True)["id"]
g.add_pair("five", "G5", "Yaw", True)

# queue: reviewer Kofi sees all five; Ama never sees her own pairs
assert len(g.list_pairs(False, exclude_contributor="Kofi")) == 5
assert [r["en"] for r in g.list_pairs(False, exclude_contributor="ama")] == ["five"]

# nobody reviews their own pair
for fn in (lambda: g.verify_pair(ids["one"], "AMA"),
           lambda: g.correct_pair(ids["one"], "ama", "X"),
           lambda: g.reject_pair(ids["one"], "Ama")):
    try: fn(); assert False
    except ValueError: pass

# approve / correct / reject by a different speaker
g.verify_pair(ids["one"], "Kofi")
r = g.correct_pair(ids["two"], "Kofi", "G2-fixed")
assert r["gjn"] == "G2-fixed" and r["original_gjn"] == "G2" and r["verified"] and r["reviewer"] == "Kofi"
r = g.reject_pair(ids["three"], "Kofi")
assert r["rejected"] and not r["verified"]

# a correction identical to the original is refused; double review is refused
try: g.correct_pair(ids["four"], "Kofi", "g4"); assert False
except ValueError: pass
try: g.verify_pair(ids["one"], "Esi"); assert False
except ValueError: pass
try: g.verify_pair("nope", "Kofi"); assert False
except KeyError: pass

# rejected pairs vanish from queue and lookups; corrected text is what gets used
assert "three" not in [r["en"] for r in g.list_pairs()]
assert g.lookup("two", "en->gjn") == "G2-fixed"
assert g.lookup("three", "en->gjn") is None      # rejected -> never used
assert g.lookup("four", "en->gjn") is None       # still unverified

st = g.stats()
assert st == {"total": 5, "verified": 2, "unverified": 2, "rejected": 1,
              "corrected": 1, "contributors": 2, "reviewers": 1}, st
print("review tests passed")
