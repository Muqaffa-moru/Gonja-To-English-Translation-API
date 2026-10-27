import json, os, sys, tempfile
tmp = tempfile.mkdtemp()
os.environ["GONJA_DATA"] = os.path.join(tmp, "pairs.jsonl")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import glossary as g
from tools import export_dataset as ex

def add_verified(n, start=0, contributor="Ama"):
    for i in range(start, start + n):
        pid = g.add_pair(f"english sentence number {i}", f"gonja phrase {i} ɛɔŋ", contributor, True)["id"]
        g.verify_pair(pid, "Kofi")

add_verified(300)
# noise that must NOT appear in the export
g.add_pair("unverified one", "unverified gonja", "Ama", True)                       # unverified
rid = g.add_pair("rejected one", "rejected gonja", "Ama", True)["id"]; g.reject_pair(rid, "Kofi")
pid = g.add_pair("variant sentence", "variant gonja A", "Ama", True)["id"]; g.verify_pair(pid, "Kofi")
pid = g.add_pair("variant sentence", "variant gonja B", "Ama", True)["id"]; g.verify_pair(pid, "Kofi")  # 2 Gonja for 1 English
pid = g.add_pair("welcome", "maraba", "Ama", True)["id"]; g.verify_pair(pid, "Kofi")
pid = g.add_pair("you are welcome", "Maraba", "Ama", True)["id"]; g.verify_pair(pid, "Kofi")             # same Gonja, 2 English
pid = g.add_pair("a", "x" * 200, "Ama", True)["id"]; g.verify_pair(pid, "Kofi")                      # misaligned length
pid = g.add_pair("same text", "same text.", "Ama", True)["id"]; g.verify_pair(pid, "Kofi")          # identical to English

out = os.path.join(tmp, "export")
stats = ex.main(["--out", out])
read = lambda n: [json.loads(l) for l in open(os.path.join(out, n + ".jsonl"), encoding="utf-8")]
tr, va, te = read("train"), read("validation"), read("test")

# right files, sensible sizes (hash split is approximate)
total = len(tr) + len(va) + len(te)
assert 290 <= total <= 306, total
assert 0.04 <= len(te) / total <= 0.17 and 0.04 <= len(va) / total <= 0.17, (len(tr), len(va), len(te))

# only verified, never rejected / unverified / bad rows
allen = {p["en"] for p in tr + va + te}
assert not ({"unverified one", "rejected one", "same text"} & allen)
assert "a" not in allen
dropped = open(os.path.join(out, "dropped.csv"), encoding="utf-8-sig").read()
assert "length ratio" in dropped and "identical to English" in dropped

# no leakage: English and Gonja are disjoint across splits
for A, B in ((tr, va), (tr, te), (va, te)):
    assert not ({p["en"] for p in A} & {p["en"] for p in B})
    assert not ({p["gjn"].lower() for p in A} & {p["gjn"].lower() for p in B})
# variants of one English sentence stay together
homes = {name for name, items in (("tr", tr), ("va", va), ("te", te)) for p in items if p["en"] == "variant sentence"}
assert len(homes) == 1, homes
# special letters survive
assert any("ɛɔŋ" in p["gjn"] for p in tr)

# STABILITY: adding data later never moves existing pairs between splits
before = {p["id"]: n for n, items in (("train", tr), ("validation", va), ("test", te)) for p in items}
add_verified(150, start=1000)
ex.main(["--out", out])
tr2, va2, te2 = read("train"), read("validation"), read("test")
after = {p["id"]: n for n, items in (("train", tr2), ("validation", va2), ("test", te2)) for p in items}
moved = [i for i in before if i in after and before[i] != after[i]]
assert not moved, moved
assert len(te2) > len(te) - 1 and {p["id"] for p in te} <= {p["id"] for p in te2}   # old test items still in test

# refuses tiny datasets
os.environ["GONJA_DATA"] = os.path.join(tmp, "tiny.jsonl")
import importlib; importlib.reload(g); importlib.reload(ex)
try: ex.main(["--out", os.path.join(tmp, "x")]); assert False
except SystemExit: pass
print("export tests passed:", stats["pairs"], "dropped", stats["dropped"])

# --- leak removal: same Gonja text with two English sentences that hash into different splits ---
def split_of(en):
    x = ex.bucket(g._norm(en), "gonja-v1")
    return "test" if x < 0.10 else "validation" if x < 0.20 else "train"
test_en = next(f"leak probe {i}" for i in range(10000) if split_of(f"leak probe {i}") == "test")
train_en = next(f"leak probe {i}" for i in range(10000) if split_of(f"leak probe {i}") == "train")
rows = [{"id": "t1", "en": test_en, "gjn": "SHARED GONJA", "verified": True},
        {"id": "r1", "en": train_en, "gjn": "shared gonja", "verified": True},
        {"id": "r2", "en": "other sentence", "gjn": "other gonja", "verified": True}]
splits, dropped = ex.build(rows)
assert [p["id"] for p in splits["test"]] == ["t1"]
assert "r1" not in {p["id"] for items in splits.values() for p in items}
assert any(d["id"] == "r1" and "appears in" in d["reason"] for d in dropped), dropped
print("leak-removal test passed")

# ---- exclude-source ----
rows = [{"id": f"s{i}", "en": f"speaker sentence {i}", "gjn": f"sg{i}", "verified": True, "contributor": "Ama"} for i in range(40)] + \
       [{"id": f"d{i}", "en": f"dictionary word {i}", "gjn": f"dg{i}", "verified": True, "contributor": "Muqaffa", "source": "Gonja Dictionary"} for i in range(40)]
splits, dropped = ex.build(rows)
assert sum(len(v) for v in splits.values()) == 80
splits, dropped = ex.build(rows, exclude_sources=("Gonja Dictionary",))
ids = {p["id"] for v in splits.values() for p in v}
assert ids and all(i.startswith("s") for i in ids) and len(ids) == 40, len(ids)
print("exclude-source test passed")
