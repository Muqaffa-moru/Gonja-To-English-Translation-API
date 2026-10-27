import os
from typing import Optional

from dotenv import load_dotenv
from fastapi.responses import FileResponse
from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException,
                     UploadFile, WebSocket, WebSocketDisconnect)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import glossary
from .khaya_service import TranslationService, TranslationUnavailable
from .languages import LANGUAGES

load_dotenv()

app = FastAPI(title="Ghana Translate API", version="0.1.0")
# Khaya is optional: without a key, data collection and review still work and
# the translation endpoints answer 503 until you add KHAYA_API_KEY.
_khaya_key = os.getenv("KHAYA_API_KEY", "").strip()
service = TranslationService(_khaya_key) if _khaya_key else None


def need_service() -> TranslationService:
    if service is None:
        raise HTTPException(status_code=503, detail="Translation is not configured: set KHAYA_API_KEY in .env")
    return service
VALID_KEYS = {k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()}
# Reviewer keys can ONLY use the review endpoints, so you can hand them to
# volunteer speakers without exposing /translate or your Khaya credit.
REVIEWER_KEYS = {k.strip() for k in os.getenv("REVIEWER_KEYS", "").split(",") if k.strip()}


def require_key(x_api_key: str = Header(default="")):
    if x_api_key not in VALID_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def require_reviewer(x_api_key: str = Header(default="")):
    if x_api_key not in VALID_KEYS | REVIEWER_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


class TextRequest(BaseModel):
    text: str
    source: str
    target: str


class Pair(BaseModel):
    english: str
    gonja: str
    contributor: str = "anonymous"
    consent: bool = False


class Review(BaseModel):
    reviewer: str


class Correction(BaseModel):
    reviewer: str
    gonja: str


def _http_error(e: Exception) -> HTTPException:
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, KeyError):
        return HTTPException(status_code=404, detail=f"Not found: {e.args[0]}")
    if isinstance(e, ValueError):
        return HTTPException(status_code=400, detail=str(e))
    if isinstance(e, TranslationUnavailable):
        return HTTPException(status_code=422, detail=str(e))
    return HTTPException(status_code=502, detail=f"Upstream failed: {e}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/languages", dependencies=[Depends(require_key)])
def languages():
    return {
        k: {"name": l.name, "text": bool(l.translate) or k == "gjn",
            "speech_in": bool(l.asr), "speech_out": bool(l.tts)}
        for k, l in LANGUAGES.items()
    }


@app.post("/contribute", dependencies=[Depends(require_key)])
def contribute(pair: Pair):
    """Step 1-3: add a Gonja <-> English pair (needs contributor consent)."""
    try:
        return glossary.add_pair(pair.english, pair.gonja, pair.contributor, pair.consent)
    except Exception as e:
        raise _http_error(e)


@app.get("/pairs", dependencies=[Depends(require_reviewer)])
def pairs(verified: Optional[bool] = None, limit: int = 50, exclude_contributor: str = ""):
    """List pairs, e.g. /pairs?verified=false&exclude_contributor=Ama for Ama's review queue."""
    return glossary.list_pairs(verified, limit, exclude_contributor)


@app.post("/pairs/{pair_id}/verify", dependencies=[Depends(require_reviewer)])
def verify(pair_id: str, review: Review):
    """Step 4: a DIFFERENT speaker marks the pair as correct."""
    try:
        return glossary.verify_pair(pair_id, review.reviewer)
    except Exception as e:
        raise _http_error(e)


@app.post("/pairs/{pair_id}/correct", dependencies=[Depends(require_reviewer)])
def correct(pair_id: str, fix: Correction):
    """Reviewer fixes the Gonja text; the original is kept in original_gjn."""
    try:
        return glossary.correct_pair(pair_id, fix.reviewer, fix.gonja)
    except Exception as e:
        raise _http_error(e)


@app.post("/pairs/{pair_id}/reject", dependencies=[Depends(require_reviewer)])
def reject(pair_id: str, review: Review):
    """Reviewer says the pair is wrong; it is excluded from lookups and training."""
    try:
        return glossary.reject_pair(pair_id, review.reviewer)
    except Exception as e:
        raise _http_error(e)


@app.get("/stats", dependencies=[Depends(require_reviewer)])
def stats():
    return glossary.stats()


@app.get("/review", include_in_schema=False)
def review_page():
    """Phone-friendly review page for the second speaker."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "review.html"))


@app.post("/translate", dependencies=[Depends(require_key)])
async def translate(req: TextRequest):
    try:
        out = await run_in_threadpool(need_service().translate_text, req.text, req.source, req.target)
    except Exception as e:
        raise _http_error(e)
    return {"source": req.source, "target": req.target, "translation": out}


@app.post("/speech-translate", dependencies=[Depends(require_key)])
async def speech_translate(
    source: str = Form(...),
    target: str = Form(...),
    audio: UploadFile = File(...),
):
    data = await audio.read()
    suffix = os.path.splitext(audio.filename or "")[1] or ".wav"
    try:
        return await run_in_threadpool(need_service().speech_to_speech, data, source, target, suffix)
    except Exception as e:
        raise _http_error(e)


@app.websocket("/ws/conversation")
async def conversation(ws: WebSocket, api_key: str = ""):
    """Client sends JSON: {"source":"tw","target":"ee","audio_b64":"..."}.
    Server replies with transcript, translation and audio_b64."""
    import base64

    if api_key not in VALID_KEYS:
        await ws.close(code=4401)
        return
    await ws.accept()
    if service is None:
        await ws.send_json({"error": "Translation is not configured: set KHAYA_API_KEY"})
        await ws.close()
        return
    try:
        while True:
            msg = await ws.receive_json()
            audio = base64.b64decode(msg["audio_b64"])
            try:
                result = await run_in_threadpool(
                    service.speech_to_speech, audio, msg["source"], msg["target"]
                )
                await ws.send_json(result)
            except Exception as e:
                await ws.send_json({"error": str(e)})
    except WebSocketDisconnect:
        pass
