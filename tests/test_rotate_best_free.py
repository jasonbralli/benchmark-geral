"""tests/test_rotate_best_free.py — suite do MONITOR de fallback free.

O script é READ-ONLY (rotação é 100% manual). Cobre:
- recommend_chain: 1 tier/provider, ordem CxB desc, top, SEM filtro de health
- parse_current_chain: extração da chain manual do config.yaml
- _health_line: marca health ruim com ⚠️
- build_alert: texto HTML com chain atual + recomendação CxB + problemas
- monitor: read-only (não escreve no config)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "rotate_best_free", ROOT / "scripts" / "rotate_best_free.py"
)
rot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rot)


def _free(cxb: float, prov: str, model_id: str) -> dict:
    return {
        "provider": prov,
        "model_id": model_id,
        "canonical_id": model_id,
        "is_free": True,
        "cxb_score": cxb,
    }


HEALTH = {
    "openrouter": {"last_ok": True, "uptime_pct": 100.0, "p50_ms": 800.0},
    "kilocode": {"last_ok": True, "uptime_pct": 22.0, "p50_ms": 770.0},
    "nvidia": {"last_ok": True, "uptime_pct": 100.0, "p50_ms": 114000.0},
    "huggingface": {"last_ok": True, "uptime_pct": 100.0, "p50_ms": 610.0},
    "novita": {"last_ok": False, "uptime_pct": 0.0, "p50_ms": 277.0},
}


def test_recommend_one_tier_per_provider():
    # mesmo modelo em 2 providers → 1 tier por provider (melhor CxB de cada)
    models = [
        _free(60.0, "kilocode", "inkling:free"),
        _free(55.0, "openrouter", "inkling:free"),
        _free(58.0, "kilocode", "outra:free"),  # mesmo provider, CxB menor
    ]
    chain = rot.recommend_chain(models, HEALTH, top=5)
    provs = [t["provider"] for t in chain]
    assert provs == ["kilocode", "openrouter"]
    # kilocode leva o melhor CxB dele (60.0)
    assert chain[0]["model"] == "inkling:free"
    assert chain[0]["cxb_score"] == 60.0


def test_recommend_order_by_cxb_desc():
    models = [
        _free(40.0, "openrouter", "a:free"),
        _free(70.0, "nvidia", "b:free"),
        _free(55.0, "kilocode", "c:free"),
    ]
    chain = rot.recommend_chain(models, HEALTH, top=5)
    assert [t["provider"] for t in chain] == ["nvidia", "kilocode", "openrouter"]


def test_recommend_top_limits_chain():
    models = [
        _free(70.0, "nvidia", "a:free"),
        _free(60.0, "kilocode", "b:free"),
        _free(50.0, "openrouter", "c:free"),
    ]
    assert len(rot.recommend_chain(models, HEALTH, top=2)) == 2


def test_recommend_no_health_filter():
    # provider com health RUIM (novita 0%) NÃO é excluído — só informativo
    models = [_free(99.0, "novita", "ling:free")]
    chain = rot.recommend_chain(models, HEALTH, top=3)
    assert len(chain) == 1
    assert chain[0]["provider"] == "novita"
    assert chain[0]["uptime_pct"] == 0.0  # health anexado, não filtra


def test_recommend_excluded_providers_skipped():
    models = [
        _free(99.0, "local-localhost-8080", "local:free"),
        _free(50.0, "openrouter", "a:free"),
    ]
    chain = rot.recommend_chain(models, HEALTH, top=5)
    assert [t["provider"] for t in chain] == ["openrouter"]


CFG = """model:
  default: x
providers:
  local: {}
fallback_providers:
  - provider: kilocode
    model: qwen/qwen3.8-27b:free
  - provider: huggingface
    model: inclusionAI/Ling-3.0-flash-Fin
  - provider: novita
    model: inclusionai/ling-3.0-flash-fin
toolsets:
  - browser
"""


def test_parse_current_chain():
    assert rot.parse_current_chain(CFG) == [
        ("kilocode", "qwen/qwen3.8-27b:free"),
        ("huggingface", "inclusionAI/Ling-3.0-flash-Fin"),
        ("novita", "inclusionai/ling-3.0-flash-fin"),
    ]


def test_parse_no_block_returns_empty():
    assert rot.parse_current_chain("model:\n  default: x\n") == []


def test_health_line_marks_bad_health():
    # novita 0% + last_ok False → ⚠️
    assert rot._health_line("novita", HEALTH).startswith("⚠️")
    # openrouter 100% → sem ⚠️
    assert not rot._health_line("openrouter", HEALTH).startswith("⚠️")
    # provider sem health → "sem health"
    assert rot._health_line("desconhecido", HEALTH) == "sem health"


def test_build_alert_has_chain_and_reco():
    res = {
        "ts": "t",
        "current": [
            {"provider": "kilocode", "model": "qwen/qwen3.8-27b:free",
             "health": "⚠️ 22% · 770ms"},
        ],
        "recommended": [
            {"provider": "nvidia", "model": "moonshotai/kimi-k3",
             "cxb_score": 68.7, "uptime_pct": 100.0, "p50_ms": 114000.0,
             "last_ok": True},
        ],
        "problems": ["kilocode/qwen: health ruim"],
    }
    txt = rot.build_alert(res)
    assert "Chain atual" in txt
    assert "kilocode" in txt and "qwen/qwen3.8-27b:free" in txt
    assert "Recomendação CxB" in txt
    assert "nvidia/moonshotai/kimi-k3" in txt
    assert "Atenção" in txt and "health ruim" in txt


def test_build_alert_no_problems_omits_section():
    res = {
        "ts": "t",
        "current": [
            {"provider": "openrouter", "model": "a:free", "health": "100% · 800ms"},
        ],
        "recommended": [],
        "problems": [],
    }
    txt = rot.build_alert(res)
    assert "Atenção" not in txt


def test_monitor_readonly(tmp_path, monkeypatch):
    # monitor não escreve no config: mesmo após monitor(), o config é intacto
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG, encoding="utf-8")
    monkeypatch.setattr(rot, "CONFIG_YAML", cfg)
    before = cfg.read_text(encoding="utf-8")
    res = rot.monitor(top=5)
    after = cfg.read_text(encoding="utf-8")
    assert before == after  # read-only
    assert len(res["current"]) == 3  # chain manual lida
    assert "recommended" in res
