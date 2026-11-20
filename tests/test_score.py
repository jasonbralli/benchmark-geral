"""Tests for benchmark_pipe.score"""
from __future__ import annotations

from benchmark_pipe.normalize import UnifiedModel
from benchmark_pipe.score import benefit, final_score, score_models


# ---------- benefit monotonicidade ----------

def test_benefit_increases_with_ctx():
    base = UnifiedModel(provider="p", model_id="x", context_k=8).to_dict() and UnifiedModel(provider="p", model_id="x", context_k=8)
    big = UnifiedModel(provider="p", model_id="x", context_k=512)
    assert benefit(big) > benefit(base)


def test_benefit_tool_call_adds() -> None:
    a = UnifiedModel(provider="p", model_id="x", context_k=128)
    b = UnifiedModel(provider="p", model_id="x", context_k=128, tool_call=True)
    assert benefit(b) == benefit(a) + 10


def test_benefit_reasoning_adds() -> None:
    a = UnifiedModel(provider="p", model_id="x", context_k=128)
    b = UnifiedModel(provider="p", model_id="x", context_k=128, reasoning=True)
    assert benefit(b) == benefit(a) + 10


def test_benefit_caps_context_at_20() -> None:
    huge = UnifiedModel(provider="p", model_id="x", context_k=1_000_000)
    # ctx=1M em K => saturado em 20
    assert benefit(huge) <= 20.0


# ---------- cxb_score ----------

def test_free_beats_paid_same_capability() -> None:
    common = dict(context_k=128, tool_call=True, reasoning=True, multimodal=False, aa_index=40)
    free = UnifiedModel(provider="nvidia", model_id="a", is_free=True, **common)
    paid = UnifiedModel(provider="openrouter", model_id="b", is_free=False, price_in=2.0, **common)
    assert final_score(free) > final_score(paid)


def test_cheaper_paid_beats_expensive_same_capability() -> None:
    common = dict(context_k=128, tool_call=True, reasoning=False, multimodal=False, is_free=False)
    cheap = UnifiedModel(provider="o", model_id="c", price_in=0.5, **common)
    exp = UnifiedModel(provider="o", model_id="e", price_in=10.0, **common)
    assert final_score(cheap) > final_score(exp)


def test_free_price_zero_handled() -> None:
    m = UnifiedModel(provider="nvidia", model_id="x", context_k=256, is_free=True)
    s = final_score(m)
    assert s > 0 and s == benefit(m)  # gratuito: desconto zero, igual ao benefit


def test_preco_desconhecido_eh_nd() -> None:
    """Preço desconhecido retorna None (N/D), não zero nem gratuito."""
    m = UnifiedModel(provider="p", model_id="x", context_k=128, tool_call=True, reasoning=True, multimodal=True, aa_index=64.6)
    assert m.price_in is None
    assert m.is_free is False
    assert final_score(m) is None


def test_preco_maior_que_desempenho_limita_a_zero() -> None:
    """Preço maior que o desempenho limita a zero, nunca negativo."""
    m = UnifiedModel(provider="p", model_id="x", context_k=8, tool_call=True, reasoning=True, multimodal=True, aa_index=0, price_in=50.0)
    assert final_score(m) == 0.0


# ---------- score_models split ----------

def test_score_models_splits_rankable() -> None:
    rankable = UnifiedModel(provider="nvidia", model_id="a", context_k=128)
    non = UnifiedModel(provider="gemini", model_id="b")  # all None
    r, n = score_models([rankable, non])
    assert len(r) == 1 and len(n) == 1
    assert r[0].performance_score > 0
    assert n[0].final_score is None


def test_score_models_orders_by_performance_desc() -> None:
    a = UnifiedModel(provider="nvidia", model_id="low", context_k=8, is_free=True)
    b = UnifiedModel(provider="nvidia", model_id="hi", context_k=1024, tool_call=True, reasoning=True, is_free=True)
    r, _ = score_models([a, b])
    assert r[0].model_id == "hi"
    assert r[1].model_id == "low"


# ---------- Regressões da nova fórmula de benefit ----------

def test_modelo_completo_aa_100_beneficio_100() -> None:
    """Modelo com todas as capacidades no máximo e AA 100 → benefit 100."""
    m = UnifiedModel(
        provider="p", model_id="complete", context_k=1_000_000,
        tool_call=True, reasoning=True, multimodal=True, aa_index=100,
    )
    assert benefit(m) == 100.0


def test_aa_50_sozinho_contribui_25() -> None:
    """AA 50 com demais componentes zerados → benefit 25."""
    m = UnifiedModel(provider="p", model_id="aa50", context_k=8, aa_index=50)
    assert benefit(m) == 25.0


def test_formula_custo_preservada() -> None:
    """Custo continua: free → final_score = benefit; pago price_in=2 → final_score = benefit - 2."""
    m_free = UnifiedModel(
        provider="p", model_id="free", context_k=128, tool_call=True,
        reasoning=True, multimodal=True, aa_index=64.6, is_free=True,
    )
    m_paid = UnifiedModel(
        provider="p", model_id="paid", context_k=128, tool_call=True,
        reasoning=True, multimodal=True, aa_index=64.6, price_in=2.0,
    )
    assert final_score(m_free) == benefit(m_free)
    assert abs(final_score(m_paid) - (benefit(m_paid) - 2.0)) < 1e-9


# ---------- Regressões: sentinelas de preço indisponível (OpenRouter -1, -1000000, NaN, Inf) ----------

def test_final_price_in_negativo_retorna_none() -> None:
    """price_in=-1 (sentinela OpenRouter) deve resultar em final_score=None, jamais bônus milionário."""
    m = UnifiedModel(
        provider="openrouter", model_id="openrouter/auto", context_k=2048,
        tool_call=True, reasoning=True, price_in=-1.0,
    )
    assert final_score(m) is None


def test_final_price_in_menos_um_milhao_retorna_none() -> None:
    """price_in=-1000000 (sentinela OpenRouter observada) → final_score=None."""
    m = UnifiedModel(
        provider="openrouter", model_id="openrouter/auto-code", context_k=128,
        tool_call=True, price_in=-1000000.0,
    )
    assert final_score(m) is None


def test_final_price_in_nan_retorna_none() -> None:
    """price_in=NaN → final_score=None (não finito, nunca bônus)."""
    m = UnifiedModel(
        provider="openrouter", model_id="openrouter/fusion", context_k=512,
        tool_call=False, price_in=float("nan"),
    )
    assert final_score(m) is None


def test_final_price_in_inf_retorna_none() -> None:
    """price_in=Inf → final_score=None (não finito, nunca bônus)."""
    m = UnifiedModel(
        provider="openrouter", model_id="openrouter/bodybuilder", context_k=256,
        tool_call=False, price_in=float("inf"),
    )
    assert final_score(m) is None


def test_usd_per_million_negativo_retorna_none() -> None:
    """_usd_per_million de preço negativo deve retornar None, nunca preço real."""
    from benchmark_pipe.normalize import _usd_per_million
    assert _usd_per_million("-1") is None
    assert _usd_per_million("-1000000") is None
    assert _usd_per_million(0.000001) == 1.0  # preço válido ainda converte normalmente
    assert _usd_per_million(None) is None
    assert _usd_per_million("abc") is None
