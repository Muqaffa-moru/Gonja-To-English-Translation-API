"""Per-service language codes, taken from the Khaya SDK language reference.
Khaya uses DIFFERENT codes per service (e.g. Ewe is 'ee' for translation but
'ewe' for ASR/TTS). None = not available on Khaya for that service."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Language:
    key: str                 # the code YOUR API users send
    name: str
    translate: Optional[str]
    asr: Optional[str]
    tts: Optional[str]


LANGUAGES = {l.key: l for l in [
    Language("en",  "English", "en",  "eng", "eng"),
    Language("tw",  "Twi",     "tw",  "twi", "twi"),
    Language("ee",  "Ewe",     "ee",  "ewe", "ewe"),
    Language("gaa", "Ga",      "gaa", "gaa", "gaa"),
    Language("dag", "Dagbani", "dag", "dag", "dag"),
    Language("fat", "Fante",   "fat", "fat", "fat"),
    Language("gur", "Gurene",  "gur", "gur", "gur"),
    Language("kus", "Kusaal",  "kus", "kus", "kus"),
    # Gonja: speech works on Khaya, translation does NOT (handled by glossary).
    Language("gjn", "Gonja",   None,  "gjn", "gjn"),
]}


def get(key: str) -> Language:
    try:
        return LANGUAGES[key]
    except KeyError:
        raise ValueError(f"Unsupported language '{key}'. Options: {', '.join(LANGUAGES)}")
