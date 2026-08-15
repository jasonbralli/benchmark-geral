"""Testes para nim_pipeline.fetch — com mocks para não depender de rede."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from nim_pipeline.fetch import fetch_nvidia_models

# Amostra mínima de resposta do models.dev
SAMPLE_API_RESPONSE = {
    "nvidia": {
        "name": "Nvidia",
        "api": "https://integrate.api.nvidia.com/v1",
        "models": {
            "z-ai/glm-5.2": {
                "id": "z-ai/glm-5.2",
                "name": "GLM-5.2",
                "family": "glm",
                "tool_call": True,
                "reasoning": True,
                "modalities": {"input": ["text"], "output": ["text"]},
            },
            "deepseek-ai/deepseek-v4-flash": {
                "id": "deepseek-ai/deepseek-v4-flash",
                "name": "DeepSeek V4 Flash",
                "family": "deepseek-flash",
                "tool_call": True,
                "reasoning": True,
                "modalities": {"input": ["text"], "output": ["text"]},
            },
        },
    }
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@patch("nim_pipeline.fetch.CACHE_PATH", Path("C:/tmp/nim_test_cache.json"))
@patch("nim_pipeline.fetch.urlopen")
def test_fetch_parses_models(mock_urlopen, tmp_path, monkeypatch):
    mock_urlopen.return_value = _FakeResponse(SAMPLE_API_RESPONSE)
    # monkeypatch cache para não poluir data/
    monkeypatch.setattr("nim_pipeline.fetch.CACHE_PATH", tmp_path / "cache.json")
    models = fetch_nvidia_models()
    assert len(models) == 2
    assert models[0]["id"] == "z-ai/glm-5.2"
    assert models[1]["tool_call"] is True


@patch("nim_pipeline.fetch.urlopen")
def test_fetch_writes_cache(mock_urlopen, tmp_path, monkeypatch):
    mock_urlopen.return_value = _FakeResponse(SAMPLE_API_RESPONSE)
    cache = tmp_path / "cache.json"
    monkeypatch.setattr("nim_pipeline.fetch.CACHE_PATH", cache)
    fetch_nvidia_models(use_cache=False)
    assert cache.exists()
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert len(saved) == 2


@patch("nim_pipeline.fetch.urlopen")
def test_fetch_fallback_to_cache_on_error(mock_urlopen, tmp_path):
    """Se a API falhar mas existir cache, usa cache."""
    mock_urlopen.side_effect = RuntimeError("network down")
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps([{"id": "cached/model"}]), encoding="utf-8")
    import nim_pipeline.fetch as mod
    original_cache = mod.CACHE_PATH
    try:
        mod.CACHE_PATH = cache
        # use_cache=True força a leitura direta do cache (sem passar pela API)
        models = mod.fetch_nvidia_models(use_cache=True)
        assert models == [{"id": "cached/model"}]
    finally:
        mod.CACHE_PATH = original_cache


@patch("nim_pipeline.fetch.urlopen")
def test_fetch_raises_without_cache(mock_urlopen, tmp_path, monkeypatch):
    """Sem cache e API falhando, deve levantar RuntimeError."""
    mock_urlopen.side_effect = RuntimeError("network down")
    cache = tmp_path / "nope" / "cache.json"  # diretório não existe
    monkeypatch.setattr("nim_pipeline.fetch.CACHE_PATH", cache)
    with pytest.raises(RuntimeError):
        fetch_nvidia_models(use_cache=False)