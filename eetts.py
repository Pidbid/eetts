"""A small, production-oriented HTTP wrapper around edge-tts."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from time import time
from typing import Annotated, Any
from uuid import uuid4

import uvicorn
from edge_tts import Communicate, voices
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import (
    APIKeyHeader,
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pydantic import BaseModel, ConfigDict, Field

VERSION = "1.1.0"
LOGGER = logging.getLogger("eetts")


def _env_int(name: str, default: int, minimum: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/output"))
MAX_TEXT_LENGTH = _env_int("MAX_TEXT_LENGTH", 5000, 1)
TTS_TIMEOUT_SECONDS = _env_int("TTS_TIMEOUT_SECONDS", 60, 1)
TTS_MAX_CONCURRENCY = _env_int("TTS_MAX_CONCURRENCY", 4, 1)
TTS_RETRIES = _env_int("TTS_RETRIES", 1, 0)
FILE_TTL_SECONDS = _env_int("FILE_TTL_SECONDS", 3600, 60)
CLEANUP_INTERVAL_SECONDS = _env_int("CLEANUP_INTERVAL_SECONDS", 300, 10)
VOICE_CACHE_SECONDS = _env_int("VOICE_CACHE_SECONDS", 3600, 60)


class TTSRequest(BaseModel):
    """Validated POST body for speech generation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    token: str | None = Field(
        default=None,
        description="Deprecated: prefer Authorization: Bearer or X-API-Key.",
    )
    voice: str = Field(default="zh-CN-XiaoxiaoNeural", min_length=1, max_length=128)
    rate: int = Field(default=0, ge=-100, le=100)
    volume: int = Field(default=0, ge=-100, le=100)
    pitch: int = Field(default=0, ge=-100, le=100)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.exception("Unable to remove temporary audio file %s", path)


def _remove_stale_files(output_dir: Path, older_than_seconds: int) -> None:
    cutoff = time() - older_than_seconds
    for path in output_dir.glob("*.mp3"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                LOGGER.info("Removed stale audio file %s", path)
        except FileNotFoundError:
            continue
        except OSError:
            LOGGER.exception("Unable to inspect or remove stale file %s", path)


async def _cleanup_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(app.state.cleanup_interval_seconds)
        await asyncio.to_thread(
            _remove_stale_files,
            app.state.output_dir,
            app.state.file_ttl_seconds,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("TOKEN must be configured before eetts can start")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app.state.token = token
    app.state.output_dir = OUTPUT_DIR
    app.state.tts_timeout_seconds = TTS_TIMEOUT_SECONDS
    app.state.tts_retries = TTS_RETRIES
    app.state.tts_semaphore = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
    app.state.file_ttl_seconds = FILE_TTL_SECONDS
    app.state.cleanup_interval_seconds = CLEANUP_INTERVAL_SECONDS
    app.state.voice_cache_seconds = VOICE_CACHE_SECONDS
    app.state.voice_cache = None
    app.state.voice_cache_expires_at = 0.0
    app.state.voice_cache_lock = asyncio.Lock()

    await asyncio.to_thread(_remove_stale_files, OUTPUT_DIR, FILE_TTL_SECONDS)
    cleanup_task = asyncio.create_task(_cleanup_loop(app), name="eetts-file-cleanup")
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(
    title="eetts",
    description="A stable HTTP wrapper around Microsoft Edge's online TTS service.",
    version=VERSION,
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
if not cors_origins:
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins != ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

bearer_scheme = HTTPBearer(auto_error=False)
header_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
query_key_scheme = APIKeyQuery(name="token", auto_error=False)


async def require_token(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    header_key: str | None = Depends(header_key_scheme),
    query_key: str | None = Depends(query_key_scheme),
) -> None:
    """Accept secure headers while retaining legacy query/body token support."""

    provided_token = bearer.credentials if bearer else header_key or query_key
    if not provided_token and request.headers.get("content-type", "").startswith(
        "application/json"
    ):
        try:
            body = await request.json()
            if isinstance(body, dict):
                provided_token = body.get("token")
        except (ValueError, TypeError):
            provided_token = None

    expected_token = request.app.state.token
    if not isinstance(provided_token, str) or not secrets.compare_digest(
        provided_token, expected_token
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def _prosody(value: int, unit: str) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value}{unit}"


async def _synthesize(request: Request, payload: TTSRequest, output_path: Path) -> None:
    last_error: Exception | None = None
    timed_out = False

    for attempt in range(request.app.state.tts_retries + 1):
        _safe_unlink(output_path)
        try:
            communicate = Communicate(
                text=payload.text,
                voice=payload.voice,
                rate=_prosody(payload.rate, "%"),
                volume=_prosody(payload.volume, "%"),
                pitch=_prosody(payload.pitch, "Hz"),
            )
            async with request.app.state.tts_semaphore:
                async with asyncio.timeout(request.app.state.tts_timeout_seconds):
                    await communicate.save(str(output_path))

            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise RuntimeError("The upstream service returned no audio")
            return
        except ValueError as exc:
            _safe_unlink(output_path)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except TimeoutError as exc:
            timed_out = True
            last_error = exc
            LOGGER.warning("TTS request timed out on attempt %d", attempt + 1)
        except Exception as exc:  # edge-tts exposes several transport exceptions
            timed_out = False
            last_error = exc
            LOGGER.warning(
                "TTS request failed on attempt %d: %s",
                attempt + 1,
                type(exc).__name__,
            )

        if attempt < request.app.state.tts_retries:
            await asyncio.sleep(min(0.25 * (2**attempt), 1.0))

    _safe_unlink(output_path)
    status_code = 504 if timed_out else 502
    detail = (
        "The upstream TTS service timed out"
        if timed_out
        else "The upstream TTS service is temporarily unavailable"
    )
    raise HTTPException(status_code=status_code, detail=detail) from last_error


async def _audio_response(
    request: Request, payload: TTSRequest, background_tasks: BackgroundTasks
) -> FileResponse:
    output_path = request.app.state.output_dir / f"{uuid4().hex}.mp3"
    await _synthesize(request, payload, output_path)
    background_tasks.add_task(_safe_unlink, output_path)
    return FileResponse(
        path=output_path,
        filename="speech.mp3",
        media_type="audio/mpeg",
    )


@app.get("/healthz", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": VERSION}


@app.get("/voices", dependencies=[Depends(require_token)], tags=["tts"])
async def list_available_voices(request: Request) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    if (
        request.app.state.voice_cache is not None
        and request.app.state.voice_cache_expires_at > loop.time()
    ):
        return {"code": 0, "message": "success", "data": request.app.state.voice_cache}

    async with request.app.state.voice_cache_lock:
        if (
            request.app.state.voice_cache is not None
            and request.app.state.voice_cache_expires_at > loop.time()
        ):
            voice_list = request.app.state.voice_cache
        else:
            try:
                async with asyncio.timeout(request.app.state.tts_timeout_seconds):
                    voice_list = await voices.list_voices()
            except TimeoutError as exc:
                raise HTTPException(
                    status_code=504, detail="The upstream voice service timed out"
                ) from exc
            except Exception as exc:
                LOGGER.warning("Unable to list voices: %s", type(exc).__name__)
                raise HTTPException(
                    status_code=502,
                    detail="The upstream voice service is temporarily unavailable",
                ) from exc

            request.app.state.voice_cache = voice_list
            request.app.state.voice_cache_expires_at = (
                loop.time() + request.app.state.voice_cache_seconds
            )

    return {"code": 0, "message": "success", "data": voice_list}


@app.get("/tts", dependencies=[Depends(require_token)], tags=["tts"])
async def tts_get(
    request: Request,
    background_tasks: BackgroundTasks,
    text: Annotated[str, Query(min_length=1, max_length=MAX_TEXT_LENGTH)],
    voice: Annotated[str, Query(min_length=1, max_length=128)] = "zh-CN-XiaoxiaoNeural",
    rate: Annotated[int, Query(ge=-100, le=100)] = 0,
    volume: Annotated[int, Query(ge=-100, le=100)] = 0,
    pitch: Annotated[int, Query(ge=-100, le=100)] = 0,
) -> FileResponse:
    payload = TTSRequest(
        text=text,
        voice=voice,
        rate=rate,
        volume=volume,
        pitch=pitch,
    )
    return await _audio_response(request, payload, background_tasks)


@app.post("/tts", dependencies=[Depends(require_token)], tags=["tts"])
async def tts_post(
    request: Request, payload: TTSRequest, background_tasks: BackgroundTasks
) -> FileResponse:
    return await _audio_response(request, payload, background_tasks)


if __name__ == "__main__":
    uvicorn.run("eetts:app", host="0.0.0.0", port=8000, log_level="info")
