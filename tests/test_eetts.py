import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import eetts


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("TOKEN", "test-token")
    monkeypatch.setattr(eetts, "OUTPUT_DIR", tmp_path)
    with TestClient(eetts.app) as test_client:
        yield test_client


class SuccessfulCommunicate:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object):
        self.kwargs = kwargs
        self.__class__.calls.append(kwargs)

    async def save(self, path: str) -> None:
        Path(path).write_bytes(b"fake-mp3")


def test_health_does_not_require_authentication(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.1.1"}


def test_protected_route_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/voices")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API token"


def test_post_accepts_legacy_body_token_and_removes_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    SuccessfulCommunicate.calls.clear()
    monkeypatch.setattr(eetts, "Communicate", SuccessfulCommunicate)

    response = client.post(
        "/tts",
        json={
            "token": "test-token",
            "text": "稳定性测试",
            "rate": -10,
            "volume": 5,
            "pitch": 0,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"fake-mp3"
    assert SuccessfulCommunicate.calls[-1]["rate"] == "-10%"
    assert SuccessfulCommunicate.calls[-1]["volume"] == "+5%"
    assert SuccessfulCommunicate.calls[-1]["pitch"] == "+0Hz"
    assert list(client.app.state.output_dir.glob("*.mp3")) == []


def test_get_accepts_bearer_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eetts, "Communicate", SuccessfulCommunicate)

    response = client.get(
        "/tts",
        params={"text": "hello", "rate": -20},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.content == b"fake-mp3"


def test_invalid_parameters_are_rejected_before_upstream_call(
    client: TestClient,
) -> None:
    response = client.get(
        "/tts",
        params={"text": "hello", "rate": -101, "token": "test-token"},
    )

    assert response.status_code == 422


def test_upstream_timeout_returns_504_and_leaves_no_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SlowCommunicate(SuccessfulCommunicate):
        async def save(self, path: str) -> None:
            await asyncio.sleep(0.05)

    monkeypatch.setattr(eetts, "Communicate", SlowCommunicate)
    client.app.state.tts_timeout_seconds = 0.01
    client.app.state.tts_retries = 0

    response = client.post(
        "/tts",
        headers={"X-API-Key": "test-token"},
        json={"text": "timeout"},
    )

    assert response.status_code == 504
    assert list(client.app.state.output_dir.glob("*.mp3")) == []


def test_transient_failure_is_retried(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FlakyCommunicate(SuccessfulCommunicate):
        attempts = 0

        async def save(self, path: str) -> None:
            self.__class__.attempts += 1
            if self.__class__.attempts == 1:
                raise ConnectionError("temporary failure")
            Path(path).write_bytes(b"recovered")

    monkeypatch.setattr(eetts, "Communicate", FlakyCommunicate)
    client.app.state.tts_retries = 1

    response = client.post(
        "/tts",
        headers={"X-API-Key": "test-token"},
        json={"text": "retry"},
    )

    assert response.status_code == 200
    assert response.content == b"recovered"
    assert FlakyCommunicate.attempts == 2


def test_concurrent_requests_use_unique_files_and_respect_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ConcurrentCommunicate(SuccessfulCommunicate):
        paths: list[str] = []
        active = 0
        max_active = 0

        async def save(self, path: str) -> None:
            self.__class__.paths.append(path)
            self.__class__.active += 1
            self.__class__.max_active = max(
                self.__class__.max_active, self.__class__.active
            )
            try:
                await asyncio.sleep(0.02)
                Path(path).write_bytes(b"concurrent")
            finally:
                self.__class__.active -= 1

    monkeypatch.setattr(eetts, "Communicate", ConcurrentCommunicate)
    client.app.state.tts_semaphore = asyncio.Semaphore(2)

    def make_request(index: int):
        return client.post(
            "/tts",
            headers={"X-API-Key": "test-token"},
            json={"text": f"request-{index}"},
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        responses = list(executor.map(make_request, range(6)))

    assert all(response.status_code == 200 for response in responses)
    assert len(set(ConcurrentCommunicate.paths)) == 6
    assert ConcurrentCommunicate.max_active == 2
    assert list(client.app.state.output_dir.glob("*.mp3")) == []


def test_voice_list_is_cached(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    list_voices = AsyncMock(return_value=[{"ShortName": "zh-CN-XiaoxiaoNeural"}])
    monkeypatch.setattr(eetts.voices, "list_voices", list_voices)

    first = client.get("/voices", headers={"X-API-Key": "test-token"})
    second = client.get("/voices", headers={"X-API-Key": "test-token"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert list_voices.await_count == 1


def test_stale_file_cleanup_only_removes_old_mp3(tmp_path: Path) -> None:
    stale_file = tmp_path / "stale.mp3"
    fresh_file = tmp_path / "fresh.mp3"
    other_file = tmp_path / "keep.txt"
    stale_file.write_bytes(b"old")
    fresh_file.write_bytes(b"new")
    other_file.write_text("keep", encoding="utf-8")
    os.utime(stale_file, (time() - 7200, time() - 7200))

    eetts._remove_stale_files(tmp_path, older_than_seconds=3600)

    assert not stale_file.exists()
    assert fresh_file.exists()
    assert other_file.exists()
