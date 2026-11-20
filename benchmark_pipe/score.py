"""benchmark_pipe.score
======================

Score de desempenho e impacto de custo:

    performance_score  0..100  (ctx log + flags + AA) — capacidade pura, sem preço.
    final_score        max(0, performance_score - price_in) — desempenho com desconto de custo.

Regras:
    - free -> performance_score (sem desconto)
    - pago com preco -> max(0, performance_score - price_in)
    - pago sem preco -> None (N/D, nao zero nem gratuito)
    - monotonico em ctx, tool_call, reasoning, multimodal, aa_index
"""

from __future__ import annotations

import math

from .normalize import UnifiedModel, is_rankable


def benefit(m: UnifiedModel) -> float:
    """Score de desempenho puro (0..100), independente de preço.

    Composição:
      - Contexto: escala logarítmica, até 20 pontos
        (min(20.0, 20.0 * (log2(max(ctx, 8)) - 3) / 14); 8K -> 0, ~1M -> 20)
      - tool_call: 10 pontos
      - reasoning: 10 pontos
      - multimodal: 10 pontos
      - AA Index: 50 * (aa_index / 100) apenas quando o índice existir;
        não são 50 pontos fixos pela simples presença do campo.

    Preço NÃO entra neste cálculo.
    """
    b = 0.0
    ctx = m.context_k or 32
    b += min(20.0, 20.0 * (math.log2(max(ctx, 8)) - 3) / 14)
    if m.tool_call:
        b += 10.0
    if m.reasoning:
        b += 10.0
    if m.multimodal:
        b += 10.0
    if m.aa_index is not None:
        b += 50.0 * (m.aa_index / 100.0)
    return round(min(b, 100.0), 2)


def final_score(m: UnifiedModel) -> float | None:
    """Desempenho com desconto linear de custo.

    Cada dólar de preço de entrada (USD/1M tokens) desconta 1 ponto
    da nota de desempenho, limitado a zero (nunca negativo).

    - Gratuito: retorna performance_score (sem desconto).
    - Pago com preço válido: max(0, performance_score - price_in).
    - Pago com preço ausente, negativo ou não finito: None (N/D),
      nunca custo zero aparente nem bônus milionário.
    """
    if m.is_free:
        return benefit(m)
    if m.price_in is None:
        return None
    import math
    if not math.isfinite(m.price_in) or m.price_in < 0:
        return None
    return round(max(0.0, benefit(m) - m.price_in), 4)


def performance_score(m: UnifiedModel) -> float:
    """Score de desempenho puro, independente de preço.

    Mede apenas capacidade (contexto, tool_call, reasoning, multimodal, AA index).
    Não varia quando o preço muda. Usado para a ordenação padrão do dashboard.
    """
    return benefit(m)


def score_models(models: list[UnifiedModel]) -> tuple[list[UnifiedModel], list[UnifiedModel]]:
    """Retorna (rankable_sorted, non_rankable_unsorted).

    rankable_sorted: modelos com is_rankable=True, scores set, ordenados desc por
    desempenho (performance_score), não por custo-benefício.
    non_rankable: passthrough (exibidos fora do rank como N/D).

    performance_score = benefit(m): desempenho puro, independente de preço.
    final_score       = max(0, performance_score - price_in): desempenho com desconto de custo.
    """
    rankable: list[UnifiedModel] = []
    non_rankable: list[UnifiedModel] = []
    for m in models:
        if is_rankable(m):
            m.performance_score = performance_score(m)
            m.final_score = final_score(m)
            rankable.append(m)
        else:
            m.performance_score = 0.0
            m.final_score = None
            non_rankable.append(m)
    rankable.sort(key=lambda x: (-x.performance_score, x.provider, x.model_id))
    return rankable, non_rankable
