# Gonja dataset format (`data/gonja_pairs.jsonl`)

One JSON object per line:

| Field | Meaning |
|---|---|
| `id` | short unique id |
| `en` | English sentence |
| `gjn` | Gonja translation, spelled the way the speaker naturally writes it |
| `contributor` | who translated it (name or nickname, for credit) |
| `consent` | always `true`; pairs are refused without it |
| `verified` | `true` once a second speaker has approved or corrected it |
| `reviewer` | who reviewed it (must differ from `contributor`) |
| `original_gjn` | the contributor's Gonja, kept when a reviewer corrected it (otherwise `null`) |
| `source` | where the pair came from, e.g. "Gonja Dictionary" (empty/`null` = written by a speaker); lets you exclude a source later |
| `rejected` | `true` if the reviewer said the pair is wrong; never used or listed again |
| `created_at` / `verified_at` | UTC timestamps |

## Review rules
- A different speaker reviews each pair: approve it, correct it, or reject it.
- A pair can be reviewed only once.
- Only `verified: true` and `rejected: false` pairs are used for lookups and training.
- Keep dialect notes out of the sentences themselves; if a speaker uses a different
  form, submit it as another pair so you can study variation later.
