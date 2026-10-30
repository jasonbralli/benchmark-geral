"""Testes do nim_pipeline.liveness — sem rede (ponto único _post mockado)."""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from nim_pipeline import liveness as lv


# ---------------------------------------------------------------- fixtures

class _FakeResp:
    """Resposta SSE falsa (iterável de linhas, context manager)."""

    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code: int, reason: str = "x") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", code, reason, hdrs=None, fp=None)


@pytest.fixture
def no_env_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)


@pytest.fixture
def env_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvk-test-123")
    return "nvk-test-123"


@pytest.fixture
def tmp_out(tmp_path):
    return tmp_path / "liveness_daily.json"


# ---------------------------------------------------------------- read_api_key

def test_read_api_key_from_env(env_key):
    assert lv.read_api_key() == "nvk-test-123"


def test_read_api_key_from_hermes_env_file(no_env_key, monkeypatch, tmp_path):
    fake = tmp_path / ".env"
    fake.write_text('FOO=bar\nNVIDIA_API_KEY="nvk-file-456"\n', encoding="utf-8")
    monkeypatch.setattr(lv, "HERMES_ENV", fake)
    assert lv.read_api_key() == "nvk-file-456"


def test_read_api_key_missing_raises(no_env_key, monkeypatch, tmp_path):
    monkeypatch.setattr(lv, "HERMES_ENV", tmp_path / "missing.env")
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        lv.read_api_key()


# ---------------------------------------------------------------- ping_model

def test_ping_ok_stream_captures_ttft(env_key, monkeypatch):
    lines = [b"data: {\"choices\":[{\"delta\":{\"content\":\"a\"}}]}\n",
             b"data: [DONE]\n"]
    monkeypatch.setattr(lv, "_post", lambda req, t: _FakeResp(lines))
    r = lv.ping_model("m/a", "k")
    assert r["alive"] is True and r["status"] == "ok" and r["http_code"] == 200
    assert r["ttft_ms"] is not None and r["total_ms"] >= 0


def test_ping_410_gone(env_key, monkeypatch):
    monkeypatch.setattr(lv, "_post", lambda req, t: (_ for _ in ()).throw(_http_error(410)))
    r = lv.ping_model("m/a", "k")
    assert r["alive"] is False and r["status"] == "gone" and r["http_code"] == 410


def test_ping_404_not_found(env_key, monkeypatch):
    monkeypatch.setattr(lv, "_post", lambda req, t: (_ for _ in ()).throw(_http_error(404)))
    r = lv.ping_model("m/a", "k")
    assert r["status"] == "not_found" and r["alive"] is False


def test_ping_429_quota(env_key, monkeypatch):
    monkeypatch.setattr(lv, "_post", lambda req, t: (_ for _ in ()).throw(_http_error(429)))
    r = lv.ping_model("m/a", "k")
    assert r["status"] == "quota" and r["alive"] is False


def test_ping_network_error(env_key, monkeypatch):
    def boom(req, t):
        raise urllib.error.URLError("conn refused")
    monkeypatch.setattr(lv, "_post", boom)
    r = lv.ping_model("m/a", "k")
    assert r["status"] == "network" and r["alive"] is False


def test_ping_request_body_shape(env_key, monkeypatch):
    """max_tokens=1, stream=true, temperature=0 — contrato do plano."""
    captured = {}

    def fake(req, t):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["auth"] = req.get_header("Authorization")
        return _FakeResp([b"data: [DONE]\n"])

    monkeypatch.setattr(lv, "_post", fake)
    lv.ping_model("m/a", "k")
    b = captured["body"]
    assert b["max_tokens"] == 1 and b["stream"] is True and b["temperature"] == 0
    assert captured["auth"] == "Bearer k"  # header presente, key nunca impressa


# ---------------------------------------------------------------- select_candidates

def test_select_candidates_filters_paid_embedding_vision():
    metas = {
        "free/chat": {"id": "free/chat", "cost": {"input": 0, "output": 0},
                      "modalities": {"input": ["text"], "output": ["text"]}},
        "paid/chat": {"id": "paid/chat", "cost": {"input": 0.5, "output": 1.0},
                      "modalities": {"input": ["text"], "output": ["text"]}},
        "x/embed": {"id": "x/embed", "family": "embed",
                    "modalities": {"input": ["text"], "output": ["text"]}},
        "vl/only": {"id": "vl/only", "cost": {"input": 0, "output": 0},
                    "modalities": {"input": ["image"], "output": ["text"]}},
        "no/meta": None,
    }
    metas = {k: v for k, v in metas.items() if v is not None}
    ids = ["free/chat", "paid/chat", "x/embed", "vl/only", "no/meta"]
    out = lv.select_candidates(ids, metas)
    assert "free/chat" in out
    assert "paid/chat" not in out      # pago conhecido
    assert "x/embed" not in out        # família excluída
    assert "vl/only" not in out        # sem texto de entrada
    assert "no/meta" in out            # sem metadado → ping decide


# ---------------------------------------------------------------- score / ordenação

def test_score_nemotron_bonus_and_dead_minus_one():
    meta = {"limit": {"context": 131072}, "tok_s": 100}
    ok = {"model_id": "nvidia/nemotron-x", "alive": True, "ttft_ms": 500}
    dead = {"model_id": "a/b", "alive": False}
    s_ok = lv.score_model(ok, meta, prev_alive=True)
    assert s_ok > 30 + 19  # nemotron + TTFT rápido + ctx + tok + prev
    assert lv.score_model(dead, meta, False) == -1.0


def test_score_ordering_alive_above_dead():
    meta = {"limit": {"context": 0}}
    a = {"model_id": "a/a", "alive": True, "ttft_ms": 900}
    b = {"model_id": "a/b", "alive": False}
    assert lv.score_model(a, meta, False) > lv.score_model(b, meta, False)


# ---------------------------------------------------------------- cache diário

def test_run_liveness_cache_same_day_no_reping(env_key, monkeypatch, tmp_out):
    today = __import__("datetime").date.today().isoformat()
    tmp_out.write_text(json.dumps({"date": today, "alive_count": 5, "results": []}),
                       encoding="utf-8")
    calls = []

    def fake_ping(mid, key, timeout):
        calls.append(mid)
        return {"model_id": mid, "alive": True, "status": "ok", "http_code": 200,
                "ttft_ms": 100, "total_ms": 120}

    monkeypatch.setattr(lv, "ping_model", fake_ping)
    res = lv.run_liveness(force=False, out_path=tmp_out, _ping=fake_ping)
    assert calls == []  # cache do dia → zero pings
    assert res["date"] == today


def test_run_liveness_force_repings_and_persists(env_key, monkeypatch, tmp_out, tmp_path):
    monkeypatch.setattr(lv, "fetch_catalog_ids", lambda key: ["m/one", "m/two"])
    monkeypatch.setattr(lv, "load_metadata", lambda: {})

    def fake_ping(mid, key, timeout):
        alive = mid == "m/one"
        return {"model_id": mid, "alive": alive, "status": "ok" if alive else "gone",
                "http_code": 200 if alive else 410, "ttft_ms": 100 if alive else None,
                "total_ms": 150 if alive else 30}

    res = lv.run_liveness(force=True, out_path=tmp_out, _ping=fake_ping)
    assert res["alive_count"] == 1
    assert res["recommended"] == "m/one"
    assert tmp_out.exists()
    saved = json.loads(tmp_out.read_text(encoding="utf-8"))
    assert saved["recommended"] == "m/one"


# ---------------------------------------------------------------- anomalias / resumo

def test_anomalies_new_dead_detected(monkeypatch, tmp_out):
    yesterday_ok = {"date": "2000-01-01", "alive_count": 2, "results": [
        {"model_id": "m/one", "alive": True}, {"model_id": "m/two", "alive": True}]}
    monkeypatch.setattr(lv, "fetch_catalog_ids", lambda key: ["m/one", "m/two"])
    monkeypatch.setattr(lv, "load_metadata", lambda: {})

    def fake_ping(mid, key, timeout):
        dead = mid == "m/two"
        return {"model_id": mid, "alive": not dead, "status": "gone" if dead else "ok",
                "http_code": 410 if dead else 200, "ttft_ms": 100, "total_ms": 150}

    # injeta prev manualmente (run_liveness lê prev do out_path)
    tmp_out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out.write_text(json.dumps(yesterday_ok), encoding="utf-8")
    res = lv.run_liveness(force=True, out_path=tmp_out, _ping=fake_ping)
    assert any(d["model_id"] == "m/two" for d in res["new_dead"])
    alert_lines = lv.anomalies(res)
    assert any("novos mortos" in a and "m/two" in a for a in alert_lines)
    assert lv.anomalies({"alive_count": 3, "new_dead": []}) == []


def test_anomalies_zero_alive():
    lines = lv.anomalies({"alive_count": 0, "new_dead": []})
    assert any("NENHUM" in a for a in lines)


def test_build_summary_contains_recommendation_and_dead():
    lv_data = {"date": "2026-10-30", "alive_count": 1, "total_candidates": 3,
               "total_catalog": 100, "recommended": "m/one",
               "results": [
                   {"model_id": "m/one", "alive": True, "status": "ok",
                    "ttft_ms": 250, "score": 41.0},
                   {"model_id": "m/two", "alive": False, "status": "gone",
                    "http_code": 410},
               ]}
    s = lv.build_summary(lv_data)
    assert "Recomendado: m/one" in s
    assert "1 vivos / 3 candidatos" in s
    assert "m/two (gone)" in s


# ---------------------------------------------------------------- liveness_map

def test_liveness_map_today_only(monkeypatch, tmp_path):
    today = __import__("datetime").date.today().isoformat()
    fresh = tmp_path / "lv.json"
    fresh.write_text(json.dumps({"date": today, "results": [
        {"model_id": "m/one", "alive": True, "status": "ok", "ttft_ms": 100}]}),
        encoding="utf-8")
    monkeypatch.setenv("LIVENESS_JSON", str(fresh))
    m = lv.liveness_map()
    assert m["m/one"]["alive"] is True

    stale = tmp_path / "lv_old.json"
    stale.write_text(json.dumps({"date": "2000-01-01", "results": [
        {"model_id": "m/one", "alive": False}]}), encoding="utf-8")
    monkeypatch.setenv("LIVENESS_JSON", str(stale))
    assert lv.liveness_map() == {}

    monkeypatch.delenv("LIVENESS_JSON")
    assert lv.liveness_map(tmp_path / "missing.json") == {}


def test_ping_label():
    assert "ok" in lv.ping_label({"alive": True, "ttft_ms": 812})
    assert "410" in lv.ping_label({"alive": False, "status": "gone", "http_code": 410})
