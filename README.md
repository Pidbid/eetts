# eetts

[![CI](https://github.com/Pidbid/eetts/actions/workflows/ci.yml/badge.svg)](https://github.com/Pidbid/eetts/actions/workflows/ci.yml)
[![GitHub release](https://img.shields.io/github/v/release/Pidbid/eetts)](https://github.com/Pidbid/eetts/releases)
[![Docker pulls](https://img.shields.io/docker/pulls/wicos/eetts)](https://hub.docker.com/r/wicos/eetts)
[![License](https://img.shields.io/github/license/Pidbid/eetts)](LICENSE)

**eetts** 是一个面向自托管场景的轻量级 Edge TTS HTTP 服务。它将 Microsoft Edge 的在线文本转语音能力封装为简单的 REST API，可用于家庭语音助手、聊天机器人、自动化流程和其他需要生成 MP3 语音的服务。

它默认提供中文语音，支持 Docker 一键部署、Bearer/API Key 鉴权、请求校验、超时与重试、并发保护及临时文件自动清理。项目重点是小而稳定，适合在 NAS、小主机或普通云服务器上长期运行。

> eetts relies on Microsoft Edge's online TTS service and therefore requires internet access. It is an unofficial wrapper and is not an offline speech engine or a Microsoft service.

## 主要特性

- 简单的 `GET /tts` 与 `POST /tts` 接口，直接返回 MP3 音频。
- 默认使用 `zh-CN-XiaoxiaoNeural`，并可通过 `/voices` 查询可用语音。
- 支持 Bearer Token 和 `X-API-Key`；旧版 query/body `token` 仍可兼容。
- 对文本长度、语速、音量和音调进行严格校验。
- 内置上游超时、指数退避重试和并发限制，避免请求堆积拖垮实例。
- 每个请求使用独立文件名，响应完成后立即清理，并定期清除异常退出遗留文件。
- 非 root 容器、健康检查、多架构镜像和固定生产依赖。
- 支持 `linux/amd64` 与 `linux/arm64`。

## 快速开始

先生成一个足够长的随机 Token，然后启动容器：

```bash
docker run -d \
  --name eetts \
  --restart unless-stopped \
  -p 8000:8000 \
  -e TOKEN='replace-with-a-long-random-token' \
  wicos/eetts:latest
```

容器启动后可以访问：

- 健康检查：`http://localhost:8000/healthz`
- OpenAPI 文档：`http://localhost:8000/docs`
- ReDoc 文档：`http://localhost:8000/redoc`

生产环境建议使用固定版本，例如 `wicos/eetts:1.1.1`，以避免升级时自动切换到行为有变化的新版本。

## API 使用

### 生成语音

推荐使用 Bearer Token：

```bash
curl --get -o speech.mp3 \
  -H 'Authorization: Bearer replace-with-a-long-random-token' \
  --data-urlencode 'text=你好，世界' \
  --data-urlencode 'voice=zh-CN-XiaoxiaoNeural' \
  --data-urlencode 'rate=-10' \
  http://localhost:8000/tts
```

POST JSON 示例：

```bash
curl -o speech.mp3 \
  -H 'X-API-Key: replace-with-a-long-random-token' \
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，世界","voice":"zh-CN-XiaoxiaoNeural","rate":0,"volume":0,"pitch":0}' \
  http://localhost:8000/tts
```

### 查询语音列表

```bash
curl \
  -H 'Authorization: Bearer replace-with-a-long-random-token' \
  http://localhost:8000/voices
```

### 接口概览

| 接口 | 鉴权 | 说明 |
| --- | --- | --- |
| `GET /healthz` | 否 | 返回服务状态和版本 |
| `GET /voices` | 是 | 返回 Edge TTS 可用语音列表，结果会在内存中缓存 |
| `GET /tts` | 是 | 使用 query 参数生成 MP3 |
| `POST /tts` | 是 | 使用 JSON 请求体生成 MP3 |
| `GET /docs` | 否 | FastAPI Swagger UI |

`/tts` 支持以下参数：

| 参数 | 默认值 | 范围或说明 |
| --- | --- | --- |
| `text` | 必填 | 非空文本，默认最长 5000 字符 |
| `voice` | `zh-CN-XiaoxiaoNeural` | Edge TTS 语音名称 |
| `rate` | `0` | `-100` 到 `100`，百分比 |
| `volume` | `0` | `-100` 到 `100`，百分比 |
| `pitch` | `0` | `-100` 到 `100`，Hz 偏移 |

为兼容旧客户端，`?token=...` 和 JSON 中的 `token` 字段仍然可用。新部署应优先使用请求头，避免 Token 出现在访问日志和浏览器历史中。

## Docker 镜像标签

同一版本出现多个标签是有意设计的，它们当前指向同一个镜像摘要，但升级策略不同：

| 标签 | 含义 | 推荐场景 |
| --- | --- | --- |
| `1.1.1` | 精确版本，发布后保持不变 | 生产环境、需要可重复部署 |
| `1.1` | `1.1.x` 系列的浮动标签；发布 `1.1.2` 后会指向新补丁版本 | 希望自动获取兼容性修复 |
| `latest` | 最新稳定版本的浮动标签 | 试用、家庭环境或手动控制升级 |

例如当前 `1.1` 和 `1.1.1` 内容相同；未来发布 `1.1.2` 时，`1.1` 会更新，而 `1.1.1` 不会变化。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | ---: | --- |
| `TOKEN` | 必填 | API Token；未设置时服务拒绝启动 |
| `OUTPUT_DIR` | `/output` | 临时音频目录 |
| `MAX_TEXT_LENGTH` | `5000` | 单次请求最大文本长度 |
| `TTS_TIMEOUT_SECONDS` | `60` | 单次上游请求超时 |
| `TTS_MAX_CONCURRENCY` | `4` | 每个 worker 的最大上游并发数 |
| `TTS_RETRIES` | `1` | 上游暂时失败后的重试次数 |
| `FILE_TTL_SECONDS` | `3600` | 异常遗留文件的清理阈值 |
| `CLEANUP_INTERVAL_SECONDS` | `300` | 遗留文件扫描间隔 |
| `VOICE_CACHE_SECONDS` | `3600` | 语音列表缓存时间 |
| `CORS_ORIGINS` | `*` | 允许的浏览器来源，多个来源使用逗号分隔 |

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
TOKEN=development-only OUTPUT_DIR=./output uvicorn eetts:app --reload
```

运行检查：

```bash
ruff check .
pytest -q
docker build -t eetts:local .
```

## 发布维护

`Publish Docker image` 工作流为 GitHub `v*` 标签构建并推送多架构镜像。仓库需要配置：

- Secret `DOCKERHUB_USERNAME`：Docker Hub 登录用户名。
- Secret `DOCKERHUB_TOKEN`：具有写权限的 Docker Hub Personal Access Token。
- Variable `DOCKERHUB_IMAGE`：完整镜像名称，例如 `wicos/eetts`。

`Sync Docker Hub description` 工作流会将本 README 同步到 Docker Hub 项目主页。发布新版本时，需要更新 `eetts.py` 中的 `VERSION` 和 [CHANGELOG.md](CHANGELOG.md)。CI 成功后，发布工作流会创建相应的 Git 标签和 GitHub Release，并请求 Docker 镜像构建。

## License

[MIT](LICENSE)
