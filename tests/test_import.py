import os, sys, tempfile

tmp = tempfile.mkdtemp()
os.environ["GONJA_DATA"] = os.path.join(tmp, "pairs.jsonl")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tools import import_csv
from app import glossary

sheet = os.path.join(tmp, "sheet.csv")
rejects = os.path.join(tmp, "rejects.csv")
with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
    f.write("Topic, English ,GONJA,Contributor\n")
    f.write("greetings,Good morning.,gonja_one,Ama\n")          # good
    f.write("greetings,Good afternoon.,,Ama\n")                 # blank -> skipped
    f.write("greetings,Thank you.,Thank you.,Ama\n")            # same as English -> reject
    f.write("greetings,Welcome.,gonja_welcome,\n")              # no contributor -> reject
    f.write("greetings,good morning,GONJA_ONE!,Yaw\n")          # duplicate of row 1
    f.write("greetings,Goodbye.,gonja_\ufffd_bye,Ama\n")        # broken chars -> reject
    f.write("greetings,How are you?,gonja_ɛɔ_how,Ama\n")        # special letters kept

# consent is mandatory for a real import
try: import_csv.main([sheet]); assert False
except SystemExit: pass

# dry run writes nothing
s = import_csv.main([sheet, "--dry-run", "--rejects", rejects])
assert s["added"] == 2 and not os.path.exists(os.environ["GONJA_DATA"]), s

# real run
s = import_csv.main([sheet, "--consent", "--rejects", rejects])
assert (s["added"], s["duplicates"], s["blank"], s["rejected"]) == (2, 1, 1, 3), s
rows = glossary.list_pairs()
assert len(rows) == 2 and all(r["consent"] and not r["verified"] for r in rows)
assert any("ɛɔ" in r["gjn"] for r in rows)          # special letters survive
assert os.path.exists(rejects)

# running it again adds nothing
s = import_csv.main([sheet, "--consent", "--rejects", rejects])
assert s["added"] == 0 and s["duplicates"] == 3, s

# default contributor rescues the row with no contributor
s = import_csv.main([sheet, "--consent", "--default-contributor", "Kofi", "--rejects", rejects])
assert s["added"] == 1 and glossary.stats()["total"] == 3, s
print("import tests passed")

# ---- "ready" and "source" columns ----
sheet2 = os.path.join(tmp, "dict.csv")
with open(sheet2, "w", encoding="utf-8-sig", newline="") as f:
    f.write("ready,english,gonja,contributor,source,note\n")
    f.write("yes,armpits,abato,Muqaffa,Gonja Dictionary,\n")          # ready -> imported with source
    f.write(",needs fixing,gonja_x,Muqaffa,Gonja Dictionary,check this\n")   # not ready -> stays in sheet
    f.write("no,also not ready,gonja_y,Muqaffa,Gonja Dictionary,\n")
    f.write("YES,dew,bunyaŋ,Muqaffa,Gonja Dictionary,\n")             # case-insensitive
s = import_csv.main([sheet2, "--consent", "--rejects", rejects])
assert (s["added"], s["not_ready"]) == (2, 2), s
by_en = {r["en"]: r for r in glossary.list_pairs(limit=500)}
assert by_en["armpits"]["source"] == "Gonja Dictionary" and by_en["armpits"]["contributor"] == "Muqaffa"
assert "needs fixing" not in by_en and "also not ready" not in by_en
# fix the row, mark it ready, import again: only that row is added
with open(sheet2, "w", encoding="utf-8-sig", newline="") as f:
    f.write("ready,english,gonja,contributor,source,note\n")
    f.write("yes,armpits,abato,Muqaffa,Gonja Dictionary,\n")
    f.write("yes,needs fixing,gonja_x_corrected,Muqaffa,Gonja Dictionary,\n")
s = import_csv.main([sheet2, "--consent", "--rejects", rejects])
assert (s["added"], s["duplicates"]) == (1, 1), s
# pairs from speakers keep source = None
assert all(r["source"] is None for r in glossary.list_pairs(limit=500) if r["contributor"] == "Ama")
print("ready/source tests passed")
