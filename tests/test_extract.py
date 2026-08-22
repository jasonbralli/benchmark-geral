"""Tests for benchmark_pipe.extract"""
from __future__ import annotations

import json
from pathlib import Path

from benchmark_pipe.extract import extract_provider_models


def test_extract_returns_dict_of_sets(tmp_path: Path):
    cache = {
        "nvidia": {"fp": "x", "at": 1, "models": ["a/b", "c/d"]},
        "openrouter": {"fp": "x", "at": 1, "models": ["e/f"]},
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cache), encoding="utf-8")
    out = extract_provider_models(cache_path=p)
    assert out["nvidia"] == {"a/b", "c/d"}
    assert out["openrouter"] == {"e/f"}
    assert all(isinstance(v, set) for v in out.values())
    assert all(isinstance(x, str) for s in out.values() for x in s)


def test_extract_missing_file_returns_empty(tmp_path: Path):
    assert extract_provider_models(tmp_path / "nope.json") == {}


def test_extract_malformed_json_returns_empty(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert extract_provider_models(p) == {}


def test_extract_skips_empty_model_ids(tmp_path: Path):
    cache = {"p": {"models": ["ok", "", None, 123, "ok2"]}}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cache), encoding="utf-8")
    out = extract_provider_models(p)
    assert out["p"] == {"ok", "ok2"}
