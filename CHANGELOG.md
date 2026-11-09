# Changelog

## 1.1.1 - 2026-11-09

- Fix speech synthesis returning HTTP 502: edge-tts 7.2.8 was rejected by the upstream WebSocket endpoint with a 403 handshake, while edge-tts 7.3.1 synthesizes normally.
- Upgrade the locked dependency set to edge-tts 7.3.1, FastAPI 0.162.0, Starlette 1.10.0, Pydantic 2.14.1, Uvicorn 0.54.0, aiohttp 3.14.5, pytest 9.2.0 and ruff 0.17.3.
- Only start automatic releases for CI runs triggered by pushes to the default branch, so pull-request CI no longer invokes the release workflow.
- Verified on Python 3.12 and 3.14: ruff passes, 10 tests pass, and a real `/tts` request returns a valid MP3.

## 1.1.0 - 2026-08-06

- Replace the per-request infinite cleanup loop with one-shot response cleanup and a bounded stale-file sweeper.
- Add unique output filenames, upstream timeouts, retry handling and a configurable concurrency limit.
- Validate text and prosody input and correctly format negative values.
- Add Bearer and `X-API-Key` authentication while retaining legacy token compatibility.
- Cache the voice list and expose an unauthenticated `/healthz` endpoint.
- Move dependency installation into the image build, run as a non-root user and disable development reload.
- Upgrade `edge-tts` from 7.0.0 to 7.2.8 and replace the withdrawn `aiohttp` 3.11.14 dependency lock.
- Add unit and concurrency tests, CI, grouped dependency updates, automated GitHub Releases and multi-architecture Docker Hub publishing.
