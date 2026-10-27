"""All provider calls live here, so adding your own Gonja model later only
touches _translate_pair()."""
import base64
import os
import tempfile

from . import glossary
from .languages import get as lang


class TranslationUnavailable(Exception):
    """Raised when no translation route exists for a language pair."""


class TranslationService:
    def __init__(self, api_key: str):
        from khaya import KhayaClient  # imported here: only needed for translation
        self.client = KhayaClient(api_key)

    # ---- text translation (always pivots through English) ----
    def _translate_pair(self, text: str, src: str, tgt: str) -> str:
        """One hop; either src or tgt is 'en'."""
        if "gjn" in (src, tgt):
            direction = "en->gjn" if src == "en" else "gjn->en"
            out = glossary.lookup(text, direction)
            if out is None:
                raise TranslationUnavailable(
                    "Gonja translation is not available yet for this phrase. "
                    "Add it via POST /contribute to grow the Gonja phrasebook."
                )
            return out
        s, t = lang(src).translate, lang(tgt).translate
        if not s or not t:
            raise TranslationUnavailable(f"No Khaya translation for {src}->{tgt}")
        return self.client.translate(text, f"{s}-{t}").text

    def translate_text(self, text: str, src: str, tgt: str) -> str:
        lang(src), lang(tgt)  # validate keys
        if src == tgt:
            return text
        if src != "en" and tgt != "en":
            text = self._translate_pair(text, src, "en")
            src = "en"
        return self._translate_pair(text, src, tgt)

    # ---- speech to text ----
    def transcribe(self, audio_bytes: bytes, src: str, suffix: str = ".wav") -> str:
        code = lang(src).asr
        if not code:
            raise ValueError(f"No speech recognition for '{src}'")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            result = self.client.transcribe(path, code)
        finally:
            os.remove(path)
        return getattr(result, "text", str(result))

    # ---- text to speech ----
    def synthesize(self, text: str, tgt: str) -> bytes:
        code = lang(tgt).tts
        if not code:
            raise ValueError(f"No text-to-speech for '{tgt}'")
        return self.client.synthesize(text, code).audio  # documented: result.audio (bytes)

    # ---- full pipeline, with graceful partial results ----
    def speech_to_speech(self, audio_bytes: bytes, src: str, tgt: str, suffix=".wav"):
        out = {"transcript": self.transcribe(audio_bytes, src, suffix),
               "translation": None, "audio_b64": None, "warnings": []}
        try:
            out["translation"] = self.translate_text(out["transcript"], src, tgt)
        except TranslationUnavailable as e:
            out["warnings"].append(str(e))
            return out
        if lang(tgt).tts:
            audio = self.synthesize(out["translation"], tgt)
            out["audio_b64"] = base64.b64encode(audio).decode()
        else:
            out["warnings"].append(f"No speech output for '{tgt}'; text only.")
        return out
