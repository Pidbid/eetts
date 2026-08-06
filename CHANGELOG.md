# Changelog

## 1.1.0 - 2026-08-06

- Replace the per-request infinite cleanup loop with one-shot response cleanup and a bounded stale-file sweeper.
- Add unique output filenames, upstream timeouts, retry handling and a configurable concurrency limit.
- Validate text and prosody input and correctly format negative values.
- Add Bearer and `X-API-Key` authentication while retaining legacy token compatibility.
- Cache the voice list and expose an unauthenticated `/healthz` endpoint.
- Move dependency installation into the image build, run as a non-root user and disable development reload.
- Upgrade `edge-tts` from 7.0.0 to 7.2.8 and replace the withdrawn `aiohttp` 3.11.14 dependency lock.
- Add unit and concurrency tests, CI, grouped dependency updates, automated GitHub Releases and multi-architecture Docker Hub publishing.
