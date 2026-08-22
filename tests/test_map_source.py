"""Tests for benchmark_pipe.map_source"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from benchmark_pipe import map_source
from benchmark_pipe.map_source import build_metadata_index, fetch_openrouter


def test_fetch_openrouter_uses_cache(tmp_path, monkeypatch):
    cache = tmp_path / "or.json"
    cache.write_text(json.dumps([{"id": "x/y"}]), encoding="utf-8")
    monkeypatch.setattr(map_source, "OR_CACHE", cache)
    out = fetch_openrouter(use_cache=True)
    assert out == [{"id": "x/y"}]


def test_fetch_openrouter_falls_back_to_cache_on_error(tmp_path, monkeypatch):
    cache = tmp_path / "or.json"
    cache.write_text(json.dumps([{"id": "cached"}]), encoding="utf-8")
    monkeypatch.setattr(map_source, "OR_CACHE", cache)

    def boom(*a, **k):
        raise OSError("net down")

    monkeypatch.setattr(map_source, "urlopen", boom)
    out = fetch_openrouter(use_cache=False)
    assert out == [{"id": "cached"}]


def test_build_metadata_index_only_known_providers(monkeypatch):
    """gemini/kilocode/huggingface/nous/opencode-free NÃO entram aqui."""
    monkeypatch.setattr(map_source, "fetch_nvidia_from_models_dev_cache", lambda: [{"id": "n1"}])
    monkeypatch.setattr(map_source, "fetch_openrouter", lambda use_cache=False: [{"id": "o1"}])
    inv = {
        "nvidia": {"a"},
        "openrouter": {"b"},
        "gemini": {"c"},
        "kilocode": {"d"},
        "huggingface": {"e"},
        "nous": {"f"},
        "opencode-free": {"g"},
    }
    out = build_metadata_index(inv, use_cache=True)
    assert set(out.keys()) == {"nvidia", "openrouter"}
    assert out["nvidia"] == [{"id": "n1"}]
    assert out["openrouter"] == [{"id": "o1"}]


def test_build_metadata_index_resilient_to_fetch_failure(monkeypatch):
    def boom():
        raise RuntimeError("x")
    def boom_legacy(**k):
        raise RuntimeError("legacy too")
    monkeypatch.setattr(map_source, "fetch_nvidia_from_models_dev_cache", boom)
    monkeypatch.setattr(map_source, "fetch_nvidia_models", boom_legacy)
    monkeypatch.setattr(map_source, "fetch_openrouter", lambda use_cache=False: [{"id": "o1"}])
    out = build_metadata_index({"nvidia": {"a"}, "openrouter": {"b"}})
    assert out["nvidia"] == []
    assert out["openrouter"] == [{"id": "o1"}]


def test_build_metadata_index_falls_back_to_legacy_project_cache(monkeypatch, tmp_path):
    """models_dev_cache ausente -> fallback p/ data/nvidia_models_raw.json (stale)."""
    def boom():
        raise RuntimeError("models_dev_cache ausente")
    fake_legacy = [{"id": "fallback/ok"}]
    monkeypatch.setattr(map_source, "fetch_nvidia_from_models_dev_cache", boom)
    monkeypatch.setattr(map_source, "fetch_nvidia_models", lambda use_cache=True: fake_legacy)
    out = build_metadata_index({"nvidia": {"a"}})
    assert out["nvidia"] == fake_legacy
