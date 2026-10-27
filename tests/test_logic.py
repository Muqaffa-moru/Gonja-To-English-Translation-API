"""Runs without a Khaya key: fakes the SDK to test routing and Gonja handling."""
import os, sys, types, tempfile

fake = types.ModuleType("khaya")
class FakeResult:  # mimics translate/synthesize/transcribe results
    def __init__(self, text=None, audio=None): self.text, self.audio = text, audio
class KhayaClient:
    def __init__(self, key): self.calls = []
    def translate(self, text, pair): self.calls.append(("translate", pair)); return FakeResult(text=f"[{pair}]{text}")
    def transcribe(self, path, code): self.calls.append(("asr", code)); return FakeResult(text="hello")
    def synthesize(self, text, code): self.calls.append(("tts", code)); return FakeResult(audio=b"RIFF")
fake.KhayaClient = KhayaClient
sys.modules["khaya"] = fake

os.environ["GONJA_DATA"] = os.path.join(tempfile.mkdtemp(), "pairs.jsonl")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import glossary
from app.khaya_service import TranslationService, TranslationUnavailable

svc = TranslationService("k")

# 1. Twi -> Ewe pivots through English using the right per-service codes
assert svc.translate_text("x", "tw", "ee") == "[en-ee][tw-en]x"
# 2. Speech pipeline uses ASR/TTS codes (not translation codes)
r = svc.speech_to_speech(b"abc", "tw", "ee")
assert ("asr", "twi") in svc.client.calls and ("tts", "ewe") in svc.client.calls
assert r["audio_b64"] and not r["warnings"]
# 3. Gonja speech in: ASR works, translation missing -> partial result with warning
r = svc.speech_to_speech(b"abc", "gjn", "ee")
assert r["transcript"] == "hello" and r["translation"] is None and r["warnings"]
# 4. After contributing a pair, Gonja -> English works via phrasebook
# unverified pairs are NOT used for translation
new = glossary.add_pair("hello", "GONJA_HELLO", contributor="Ama", consent=True)
assert new["duplicate"] is False
try: svc.translate_text("GONJA_HELLO", "gjn", "en"); assert False
except TranslationUnavailable: pass
# consent is required, same person cannot verify, a second speaker can
try: glossary.add_pair("a", "b", consent=False); assert False
except ValueError: pass
try: glossary.verify_pair(new["id"], "ama"); assert False
except ValueError: pass
glossary.verify_pair(new["id"], "Kofi")
assert glossary.add_pair("Hello!", "gonja_hello", "Yaw", True)["duplicate"] is True   # same pair, case/punct ignored
assert glossary.add_pair("hello", "GONJA_HELLO_VARIANT", "Yaw", True)["duplicate"] is False  # dialect variant is kept
st = glossary.stats()
assert st["verified"] == 1 and st["total"] == 2, st
assert len(glossary.list_pairs(verified=False)) == 1
assert svc.translate_text("GONJA_HELLO", "gjn", "en") == "hello"
r = svc.speech_to_speech(b"abc", "en", "gjn")  # asr says "hello" -> glossary en->gjn
assert r["translation"] == "GONJA_HELLO" and ("tts", "gjn") in svc.client.calls
# 5. Unknown language rejected
try: svc.translate_text("x", "xx", "en"); assert False
except ValueError: pass
print("all tests passed")
