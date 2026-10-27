# Ghana Translate API

Live translation between Ghanaian languages (and English), built on the Khaya API.
Pipeline: speech -> text (ASR) -> translate (pivot via English) -> speech (TTS).

## Start here (macOS / Linux): data collection + review, no Khaya key needed
Needs Python 3.9 or newer (3.11 or 3.12 recommended): check with `python3 --version`.
If `pip install` fails with errors mentioning `maturin`, `setuptools` or Rust, your Python or pip is too old.
Run `python -m pip install --upgrade pip` first; if that is not enough, install a newer Python and recreate the venv (`rm -rf venv`).

```bash
cd ghana-translate-api
python3 -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                  # then edit .env: make up API_KEYS and REVIEWER_KEYS
python3 tools/import_csv.py gonja_prompts.csv --dry-run     # preview your sheet
python3 tools/import_csv.py gonja_prompts.csv --consent     # import it

uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/review on your own computer to test the review page.
(Use a name that is not your contributor name, e.g. "Tester", and one of your REVIEWER_KEYS.)

Translation (later): add `KHAYA_API_KEY` to `.env` and run `pip install -r requirements-translate.txt`.
Interactive docs: http://127.0.0.1:8000/docs

### Letting reviewers reach it from their phones
The server runs on your computer, so your reviewers need a way to reach it:
- **Same Wi-Fi (simplest):** start with `uvicorn app.main:app --host 0.0.0.0`, find your computer's address (macOS: `ipconfig getifaddr en0`), and send `http://THAT-ADDRESS:8000/review`. Trusted networks only: there is no HTTPS.
- **Anywhere (temporary link):** run a tunnel while they review, e.g. Cloudflare's `cloudflared tunnel --url http://localhost:8000` (macOS: `brew install cloudflared`) or ngrok. Send them the https link it prints plus `/review`.
- Your computer must stay on, and the server and tunnel running, while they review. Your data stays in `data/gonja_pairs.jsonl` on your machine.

## Try it
```bash
# Text: Twi -> Ewe (pivots through English automatically)
curl -X POST http://127.0.0.1:8000/translate \
  -H "X-API-Key: dev-key-123" -H "Content-Type: application/json" \
  -d '{"text":"Me ho yɛ","source":"tw","target":"ee"}'

# Speech: upload audio, get transcript + translation + audio back
curl -X POST http://127.0.0.1:8000/speech-translate \
  -H "X-API-Key: dev-key-123" \
  -F source=tw -F target=ee -F audio=@hello.wav
```

## Live conversation (WebSocket)
Connect to `ws://HOST/ws/conversation?api_key=dev-key-123` and send:
`{"source":"tw","target":"ee","audio_b64":"<base64 audio>"}`
You get back `transcript`, `translation`, `audio_b64`.

## Gonja support
- **Speech in/out: yes.** Khaya has Gonja (`gjn`) for speech recognition and text-to-speech.
- **Translation: not on Khaya.** Gonja is not in Khaya's translation pairs, so this API uses a local phrasebook (`data/gonja_pairs.jsonl`, exact-phrase match only).
- If a phrase isn't in the phrasebook, the API returns the transcript plus a warning instead of failing.
- Dataset format: see `data/SCHEMA.md`. Pairs live in `data/gonja_pairs.jsonl`.

### Collecting Gonja data (Step 1)
```bash
# 1. A speaker adds a pair (consent is required)
curl -X POST http://127.0.0.1:8000/contribute -H "X-API-Key: dev-key-123" \
  -H "Content-Type: application/json" \
  -d '{"english":"Good morning","gonja":"<verified Gonja phrase>","contributor":"Ama","consent":true}'

# 2. A DIFFERENT speaker sees the review queue ...
curl "http://127.0.0.1:8000/pairs?verified=false" -H "X-API-Key: dev-key-123"
# 3. ... and verifies a pair by its id
curl -X POST http://127.0.0.1:8000/pairs/<id>/verify -H "X-API-Key: dev-key-123" \
  -H "Content-Type: application/json" -d '{"reviewer":"Kofi"}'

# Progress
curl http://127.0.0.1:8000/stats -H "X-API-Key: dev-key-123"
```
- Only **verified** pairs are used for translation lookups and training. To test before anyone has verified, set `GONJA_REQUIRE_VERIFIED=false`.
- The same person cannot verify their own pair.
- `data/template.csv` is a sheet for speakers who prefer to fill in rows offline (import it with `tools/import_csv.py`).
- Replace `_translate_pair()` in `app/khaya_service.py` when your own model is ready.

### Reviewing pairs (Step 4)
A different Gonja speaker checks every pair, on their phone:

1. Put a key for volunteers in `.env`: `REVIEWER_KEYS=reviewer-key-456`. Reviewer keys can **only** use the review endpoints, not `/translate`, so your Khaya credit stays safe.
2. Run the server where the reviewer can reach it (deploy it, or use a temporary tunnel such as ngrok or Cloudflare Tunnel; use HTTPS because the key is typed into the page).
3. Send the reviewer `https://YOUR-SERVER/review`, their reviewer key, and ask them to use their own name.
4. They see one pair at a time:
   - ✅ **Correct**: approves it
   - ✏️ **Fix it**: replaces the Gonja with theirs (your original is kept in `original_gjn`)
   - 🚫 **Wrong**: removes the pair from the dataset
   - ⏭ **Skip**: comes back later
- Reviewers never see pairs they contributed themselves, and nobody can review a pair twice.
- Rejected pairs are never used. Progress: `GET /stats`.
- The same actions exist as API calls: `POST /pairs/{id}/verify`, `/correct`, `/reject`.
- Reviewer identity is trust-based (the name they type). Give keys only to people you trust.

### Importing filled sheets (Step 3)
```bash
# 1. Preview: checks the files, writes nothing
python tools/import_csv.py sheets/ --dry-run

# 2. Import for real (--consent = every speaker agreed to storage + training use)
python tools/import_csv.py sheets/ --consent

# Sheet without a contributor column filled in
python tools/import_csv.py kofi.csv --consent --default-contributor Kofi
```
- Accepts files or whole folders of `.csv` files; blank Gonja cells are skipped.
- Rejected rows are listed in `rejects.csv` with the reason (missing contributor, Gonja identical to English, broken characters, too long).
- Safe to re-run: duplicates are skipped.
- Excel tip: save as **CSV UTF-8**, or special letters (ɛ, ɔ) get damaged.
- Imported pairs start **unverified**; a different speaker checks them in Step 4 (see above).
- Privacy: `data/gonja_pairs.jsonl` contains contributor names. It is git-ignored; don't publish it without contributors' permission.

### Using the Gonja Dictionary (words and examples)
Two sheets made from the dictionary: `dictionary_words.csv` (Gonja word, English meaning) and `dictionary_examples.csv`
(Gonja phrase or sentence, English translation). Both have you as contributor and a `source` column
("Gonja Dictionary (words)" / "Gonja Dictionary (examples)").

1. Put both files in `sheets/`.
2. The **`ready`** column decides what is imported: only rows marked `yes`. Rows that need a look have it blank
   and a reason in the **`note`** column (long English, a "?", an affix, no translation found, several examples run together).
3. Fix a row (correct the Gonja or English, split merged examples into separate rows), then type `yes` in `ready`.
4. Import whenever you like. Already imported rows are skipped, so you can import again after each round of fixes:
   ```bash
   python tools/import_csv.py sheets/ --dry-run
   python tools/import_csv.py sheets/ --consent
   ```
5. **Do not change a row after it has been imported** (the old version would stay and the new one would be added as a second pair).
   Fix first, then mark ready. A second speaker can still correct imported pairs on the review page.
- The words sheet is single words, so it would dominate the dataset. For a sentence-only test set, leave the words out:
  `python tools/export_dataset.py --exclude-source "Gonja Dictionary (words)"`
- Check that you have permission to train on the dictionary. The `source` field lets you leave it out later with `--exclude-source`.

### Cleaning and splitting the data (Step 5)
```bash
python tools/export_dataset.py                 # writes export/train.jsonl, validation.jsonl, test.jsonl
python tools/export_dataset.py --dry-run       # just show the counts
```
- Uses **verified** pairs only (rejected and unreviewed pairs are never exported).
- Cleans text (Unicode NFC, tidy spaces) and drops broken rows into `export/dropped.csv` with the reason.
- Split is about 80% train, 10% validation, 10% test, decided by a hash of the English sentence, so:
  - all Gonja variants of one sentence stay in the same split;
  - **pairs never move between splits when you add more data later**, so your test set stays fixed and scores stay comparable;
  - keep the default `--seed` forever.
- Pairs whose Gonja text appears in a later split are removed from the earlier one (no leakage into test).
- `export/stats.json` summarises the result. Fewer than 20 usable pairs: the tool refuses.
- Demo only: `--include-unverified` shows the format before anyone has reviewed. Never train on that output.
- Privacy: `export/` is git-ignored. Share the dataset publicly only with contributors' permission.

## Language codes
Khaya uses different codes per service (Ewe is `ee` for translation, `ewe` for speech). `app/languages.py` maps your API's keys (`tw`, `ee`, `gjn`, ...) to the right code for each service. `GET /languages` shows what each language supports.

## Tests
`python tests/test_logic.py` runs without a Khaya key (it fakes the SDK).

## Still to verify with a real key
- Audio format your phone records vs what Khaya ASR accepts (WAV is safest).
- Khaya's terms and rate limits if you expose this publicly.

## Deploy
Render or Railway: build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
Set `KHAYA_API_KEY` and `API_KEYS` as environment variables there, not in git. Add `.env` to `.gitignore`.
# Gonja-To-English-Translation-API
