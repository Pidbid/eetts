# eetts

A small, stable HTTP service for Microsoft Edge's online text-to-speech service. It supports Docker, Bearer/API-key authentication, bounded concurrency, retries, timeouts and automatic temporary-file cleanup.

## Docker

```bash
docker run -d \
  --name eetts \
  --restart unless-stopped \
  -p 8000:8000 \
  -e TOKEN='replace-with-a-long-random-token' \
  your-dockerhub-user/eetts:latest
```

Replace the image name with your Docker Hub image, for example `your-dockerhub-user/eetts:latest`.

The container includes a health check at `GET /healthz`. API documentation is available at `http://localhost:8000/docs`.

## API

Bearer authentication is recommended:

```bash
curl -o speech.mp3 \
  -H 'Authorization: Bearer replace-with-a-long-random-token' \
  'http://localhost:8000/tts?text=你好，世界&rate=-10'
```

POST example:

```bash
curl -o speech.mp3 \
  -H 'X-API-Key: replace-with-a-long-random-token' \
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，世界","voice":"zh-CN-XiaoxiaoNeural","rate":0,"volume":0,"pitch":0}' \
  http://localhost:8000/tts
```

For compatibility, `?token=...` and the old JSON `token` field are still accepted. Headers are preferable because query tokens may be recorded in logs and browser history.

## Configuration

| Variable | Default | Description |
| --- | ---: | --- |
| `TOKEN` | required | API token; the service refuses to start when it is missing |
| `OUTPUT_DIR` | `/output` | Temporary audio directory |
| `MAX_TEXT_LENGTH` | `5000` | Maximum request text length |
| `TTS_TIMEOUT_SECONDS` | `60` | Timeout for one upstream attempt |
| `TTS_MAX_CONCURRENCY` | `4` | Maximum simultaneous upstream calls per worker |
| `TTS_RETRIES` | `1` | Retry count after transient upstream failures |
| `FILE_TTL_SECONDS` | `3600` | Age at which crash leftovers are removed |
| `CLEANUP_INTERVAL_SECONDS` | `300` | Interval between stale-file scans |
| `VOICE_CACHE_SECONDS` | `3600` | Voice-list cache lifetime |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins |

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
TOKEN=development-only OUTPUT_DIR=./output uvicorn eetts:app --reload
```

Run validation with:

```bash
ruff check .
pytest -q
docker build -t eetts:local .
```

## Docker Hub publishing

The `Publish Docker image` workflow builds `linux/amd64` and `linux/arm64` images whenever a `v*` tag is created. Configure these under **Repository settings → Secrets and variables → Actions**:

- Secret `DOCKERHUB_USERNAME`: Docker Hub login name.
- Secret `DOCKERHUB_TOKEN`: a Docker Hub personal access token with write permission.
- Variable `DOCKERHUB_IMAGE`: complete image name, such as `pidbid/eetts`.

If these values are not configured, a release still succeeds and Docker publication is safely skipped. After configuring them, open **Actions → Publish Docker image → Run workflow** and enter an existing tag such as `v1.1.0`.

## Releases

After CI succeeds on `main`, the release workflow reads `VERSION` from `eetts.py`. If that version has not been published, it creates the corresponding `v*` tag and GitHub Release, then requests Docker publication. Bump `VERSION` and update [CHANGELOG.md](CHANGELOG.md) for every new release. Manually pushed `v*` tags are also supported.
