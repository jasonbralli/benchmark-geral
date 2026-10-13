"""Testes do resumo de saúde do curate_daily (stdout do cron = canal único).

Contexto (13/10/2026): o cron 47fa2a4a rodava o probe 2x (full + light) e
cada script imprimia sua lista de falha → providers duplicados na mensagem
do Telegram. Além disso, probe_run(alert=False) NÃO filtra `alerts:false`
→ openai/anthropic (falham por design, sem key) vazavam como 🏥 Falha.
_format_health_summary filtra, categoriza e compacta.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from curate_daily import _format_health_summary  # noqa: E402


def _cfg() -> dict:
    return {
        "providers": {
            "nvidia": {}, "gemini": {}, "kilocode": {}, "groq": {},
            "openai": {"alerts": False}, "anthropic": {"alerts": False},
        },
        "alert": {"consecutive_threshold": 3, "latency_threshold_ms": 5000},
    }


def _agg() -> dict:
    return {
        "nvidia": {"uptime_pct": 100.0},
        "gemini": {"uptime_pct": 100.0},
        "kilocode": {"uptime_pct": 0.0},
        "groq": {"uptime_pct": 50.0},
        "openai": {"uptime_pct": 0.0},
        "anthropic": {"uptime_pct": 0.0},
    }


def test_by_design_nao_vaza_na_falha_real():
    """openai/anthropic (alerts:false) ficam na linha 🚫, nunca na 🏥."""
    out = _format_health_summary(
        ["kilocode", "openai", "anthropic"], _cfg(), _agg()
    )
    fail = [l for l in out if l.startswith("🏥")]
    assert len(fail) == 1
    assert "kilocode" in fail[0]
    assert "openai" not in fail[0]
    assert "anthropic" not in fail[0]


def test_ok_inclui_providers_saudaveis():
    """Resposta ao 'cadê Google e NVIDIA': 🟢 OK lista os verdes."""
    out = _format_health_summary(["kilocode", "openai"], _cfg(), _agg())
    ok = [l for l in out if l.startswith("🟢")]
    assert len(ok) == 1
    assert "nvidia" in ok[0]
    assert "gemini" in ok[0]


def test_instavel_fica_em_categoria_propria():
    """Provider que não alertou mas tem uptime <100% vira 🟡 com o %."""
    out = _format_health_summary(["kilocode"], _cfg(), _agg())
    yellow = [l for l in out if l.startswith("🟡")]
    assert len(yellow) == 1
    assert "groq (50.0%)" in yellow[0]


def test_by_design_agrupado_em_linha_unica():
    out = _format_health_summary(
        ["kilocode", "openai", "anthropic"], _cfg(), _agg()
    )
    des = [l for l in out if l.startswith("🚫")]
    assert len(des) == 1
    assert "openai" in des[0] and "anthropic" in des[0]
    assert "Sem credencial" in des[0]


def test_by_design_saudavel_vai_para_ok():
    """Se um dia ganhar key e ficar verde, aparece como OK (não 🚫)."""
    agg = _agg()
    agg["openai"] = {"uptime_pct": 100.0}
    out = _format_health_summary(["kilocode"], _cfg(), agg)
    ok = [l for l in out if l.startswith("🟢")][0]
    assert "openai" in ok
    assert not [l for l in out if l.startswith("🚫")]


def test_sem_duplicacao_de_provider():
    """Cada provider aparece em no máximo 1 linha do resumo."""
    out = _format_health_summary(
        ["kilocode", "openai", "anthropic"], _cfg(), _agg()
    )
    joined = " ".join(out)
    for p in ("nvidia", "gemini", "kilocode", "groq", "openai", "anthropic"):
        # nome pode aparecer 1x como provider; contagem entre vírgulas
        assert joined.count(p) == 1, f"{p} duplicado em: {out}"
