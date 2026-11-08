"""tests/test_rotate_best_free.py — suite do MONITOR de fallback free.

O script é READ-ONLY (rotação é 100% manual). Cobre:
- recommend_chain: 4 filtros (free + vivo/liveness ok + CxB > 50 + com AA),
  ordem CxB desc, top.
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


def _free(cxb: float, prov: str, model_id: str, aa: float = 10.0) -> dict:
    return {
        "provider": prov,
        "model_id": model_id,
        "canonical_id": model_id,
        "is_free": True,
        "cxb_score": cxb,
        "aa_index": aa,
    }


def _lv(model_id: str, status: str = "ok", alive: bool = True) -> dict:
    return {"model_id": model_id, "status": status, "alive": alive, "ttft_ms": 500}


HEALTH = {
    "openrouter": {"last_ok": True, "uptime_pct": 100.0, "p50_ms": 800.0},
    "kilocode": {"last_ok": True, "uptime_pct": 22.0, "p50_ms": 770.0},
    "nvidia": {"last_ok": True, "uptime_pct": 100.0, "p50_ms": 114000.0},
    "huggingface": {"last_ok": True, "uptime_pct": 100.0, "p50_ms": 610.0},
    "novita": {"last_ok": False, "uptime_pct": 0.0, "p50_ms": 277.0},
}

LIVENESS = {
    "inkling:free": _lv("inkling:free"),
    "outra:free": _lv("outra:free"),
    "a:free": _lv("a:free"),
    "b:free": _lv("b:free"),
    "c:free": _lv("c:free"),
    "x:free": _lv("x:free"),
    "ling:free": _lv("ling:free"),
    "local:free": _lv("local:free"),
    "sem_aa:free": _lv("sem_aa:free"),
    "morto:free": _lv("morto:free", status="not_found", alive=False),
    "nao_ok:free": _lv("nao_ok:free", status="unverified", alive=True),
}


def test_recommend_top_by_cxb_desc():
    models = [
        _free(70.0, "nvidia", "b:free"),
        _free(60.0, "kilocode", "c:free"),
        _free(55.0, "openrouter", "a:free"),
    ]
    chain = rot.recommend_chain(models, HEALTH, LIVENESS, top=5)
    assert [t["provider"] for t in chain] == ["nvidia", "kilocode", "openrouter"]


def test_recommend_sem_dedup_por_provider():
    # mesmo modelo em 2 providers entra pelos 2 (sem dedup por provider)
    models = [
        _free(70.0, "nvidia", "x:free"),
        _free(65.0, "openrouter", "x:free"),
    ]
    chain = rot.recommend_chain(models, HEALTH, LIVENESS, top=5)
    assert len(chain) == 2


def test_recommend_filtro_cxb_maior_que_50():
    models = [
        _free(60.0, "nvidia", "a:free"),
        _free(50.0, "nvidia", "b:free"),
        _free(49.0, "nvidia", "c:free"),
    ]
    chain = rot.recommend_chain(models, HEALTH, LIVENESS, top=5)
    assert len(chain) == 1
    assert chain[0]["model"] == "a:free"


def test_recommend_filtro_com_aa():
    # sem aa_index → fica de fora
    models = [_free(99.0, "nvidia", "sem_aa:free")]
    models[0]["aa_index"] = None
    chain = rot.recommend_chain(models, HEALTH, LIVENESS, top=5)
    assert chain == []


def test_recommend_somente_vivos():
    # liveness não ok → fica de fora
    chain = rot.recommend_chain(
        [_free(99.0, "nvidia", "morto:free")],
        HEALTH, {"morto:free": LIVENESS["morto:free"]}, top=5,
    )
    assert chain == []
    # status unverified (sem TTFT) também não conta como vivo
    chain = rot.recommend_chain(
        [_free(99.0, "nvidia", "nao_ok:free")],
        HEALTH, {"nao_ok:free": LIVENESS["nao_ok:free"]}, top=5,
    )
    assert chain == []


def test_recommend_top_limita_chain():
    models = [
        _free(70.0, "nvidia", "a:free"),
        _free(60.0, "kilocode", "b:free"),
        _free(55.0, "openrouter", "c:free"),
    ]
    assert len(rot.recommend_chain(models, HEALTH, LIVENESS, top=2)) == 2


def test_recommend_health_nao_filtra_recomendacao():
    # provider com health ruim (novita 0%) não exclui da recomendação (só informativo)
    models = [_free(99.0, "novita", "ling:free")]
    chain = rot.recommend_chain(models, HEALTH, LIVENESS, top=3)
    assert len(chain) == 1
    assert chain[0]["provider"] == "novita"


def test_recommend_excluded_providers_skipped():
    models = [
        _free(99.0, "local-localhost-8080", "local:free"),
        _free(60.0, "openrouter", "a:free"),
    ]
    chain = rot.recommend_chain(models, HEALTH, LIVENESS, top=5)
    assert [t["provider"] for t in chain] == ["openrouter"]


def test_recommend_liveness_ausente_fica_de_fora():
    # sem dado de liveness → não é provado vivo → fica de fora
    chain = rot.recommend_chain(
        [_free(99.0, "nvidia", "nenhum:free")], HEALTH, {}, top=5
    )
    assert chain == []


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
    assert rot._health_line("novita", HEALTH).startswith("⚠️")
    assert not rot._health_line("openrouter", HEALTH).startswith("⚠️")
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
             "last_ok": True, "aa_index": 12.0},
        ],
        "problems": ["kilocode/qwen: health ruim"],
    }
    txt = rot.build_alert(res)
    assert "Chain atual" in txt
    assert "kilocode" in txt and "qwen/qwen3.8-27b:free" in txt
    assert "Recomendação CxB" in txt
    assert "nvidia/moonshotai/kimi-k3" in txt
    assert "CxB 68.7" in txt and "AA 12.0" in txt
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
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CFG, encoding="utf-8")
    monkeypatch.setattr(rot, "CONFIG_YAML", cfg)
    before = cfg.read_text(encoding="utf-8")
    res = rot.monitor(top=5)
    after = cfg.read_text(encoding="utf-8")
    assert before == after  # read-only
    assert len(res["current"]) == 3  # chain manual lida
    assert "recommended" in res
