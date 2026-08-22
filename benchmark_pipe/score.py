"""benchmark_pipe.score
======================

Score custo x beneficio:

    benefit(m)  0..100  (ctx log + flags + AA)
    cxb(m)      benefit / (cost + 1)   (eps=1 -> free domina; pagos B/C)

Regras:
    - free -> cost=0
    - pago sem preco -> cost=0 (mas is_free=False -> nao domina; apenas ranking neutro)
    - monotonico em ctx, tool_call, reasoning, multimodal, aa_index
"""

from __future__ import annotations

import math

from .normalize import UnifiedModel, is_rankable


def benefit(m: UnifiedModel) -> float:
    """0..100 com pesos: ctx<=40, tool_call=15, reasoning=15, multimodal=10, AA<=20."""
    b = 0.0
    ctx = m.context_k or 32
    # 8K -> 0 ; ~1M -> 40   (escala log2)
    b += min(40.0, 40.0 * (math.log2(max(ctx, 8)) - 3) / 14)
    if m.tool_call:
        b += 15.0
    if m.reasoning:
        b += 15.0
    if m.multimodal:
        b += 10.0
    if m.aa_index is not None:
        b += 20.0 * (m.aa_index / 100.0)
    return round(b, 2)


def cxb_score(m: UnifiedModel) -> float:
    cost = 0.0 if m.is_free else (m.price_in or 0.0)
    return round(benefit(m) / (cost + 1.0), 4)


def score_models(models: list[UnifiedModel]) -> tuple[list[UnifiedModel], list[UnifiedModel]]:
    """Retorna (rankable_sorted, non_rankable_unsorted).

    rankable_sorted: modelos com is_rankable=True, cxb_score set, ordenados desc.
    non_rankable: passthrough (exibidos fora do rank como N/D).
    """
    rankable: list[UnifiedModel] = []
    non_rankable: list[UnifiedModel] = []
    for m in models:
        if is_rankable(m):
            m.cxb_score = cxb_score(m)
            rankable.append(m)
        else:
            m.cxb_score = 0.0
            non_rankable.append(m)
    rankable.sort(key=lambda x: (-x.cxb_score, x.provider, x.model_id))
    return rankable, non_rankable
