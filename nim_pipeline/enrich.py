"""
nim_pipeline.enrich
===================

Enriquece os modelos filtrados com dados da **Artificial Analysis Intelligence
Index v4.1** (third-party score 0-100).

Estratégia em camadas (graceful degradation):
    1. **Cache estático** embutido em `AA_INTELLIGENCE_INDEX` (curado manualmente)
    2. **Refresh opcional** via web_search quando o `EnrichRunner` recebe hook
       externo (ex: durante cronjob, o Hermes agent atualiza o cache)

Uso básico (offline):
    from nim_pipeline.enrich import enrich_models_with_aa
    enriched = enrich_models_with_aa(frontier_models)

Calibração de estrelas:
    5★ ≥50 | 4★ ≥35 | 3★ ≥20 | 2★ ≥10 | 1★ <10 | N/D se None
"""

from __future__ import annotations

from typing import Any

AA_BASE = "https://artificialanalysis.ai/models/"

# Curated snapshot do AA Intelligence Index v4.1 (atualizado em 14/08/2026).
# Scores coletados via web_search em https://artificialanalysis.ai/models/{slug}
AA_INTELLIGENCE_INDEX: dict[str, dict[str, Any]] = {
    "thinkingmachines/inkling": {
        "index": 41,
        "url": "https://artificialanalysis.ai/models/inkling",
    },
    "z-ai/glm-5.2": {
        "index": 51,
        "url": "https://artificialanalysis.ai/models/glm-5-2",
    },
    "moonshotai/kimi-k2.6": {
        "index": 43,
        "url": "https://artificialanalysis.ai/models/moonshot-kimi-k2",
    },
    "nvidia/nemotron-3-ultra-550b-a55b": {
        "index": 38,
        "url": "https://artificialanalysis.ai/models/nvidia-nemotron-3-ultra-550b-a55b",
    },
    "nvidia/nemotron-3-super-120b-a12b": {
        "index": 26,
        "url": "https://artificialanalysis.ai/models/nvidia-nemotron-3-super-120b-a12b",
    },
    "minimaxai/minimax-m3": {
        "index": 44,
        "url": "https://artificialanalysis.ai/models/minimax-m3",
    },
    "openai/gpt-oss-120b": {
        "index": 24,
        "url": "https://artificialanalysis.ai/models/gpt-oss-120b",
    },
    "deepseek-ai/deepseek-v4-flash-0731": {
        "index": 50,
        "url": "https://artificialanalysis.ai/models/deepseek-v4-flash",
        "display_name": "deepseek-ai/deepseek-v4-flash-0731",
    },
    "deepseek-ai/deepseek-v4-flash": {
        "index": 50,
        "url": "https://artificialanalysis.ai/models/deepseek-v4-flash",
        # O endpoint NIM sem sufixo corresponde ao checkpoint V4-Flash-0731 (31/jul/2026).
        # Exibimos o nome versionado para refletir o modelo real servido pela API.
        "display_name": "deepseek-ai/deepseek-v4-flash-0731",
    },
    "deepseek-ai/deepseek-v4-pro": {
        "index": None,
        "url": "https://artificialanalysis.ai/models/deepseek-v4-pro",
    },
    "poolside/laguna-xs-2.1": {"index": None, "url": None},
    "mistralai/mistral-large-3-675b-instruct-2512": {
        "index": None,
        "url": "https://artificialanalysis.ai/models/mistral-large-3-675b-instruct-2512",
    },
    "nvidia/nemotron-3.5-lightning-30b-a3b": {
        "index": None,
        "url": None,  # Modelo muito novo (11/08/2026) — sem score ainda
    },
    "minimaxai/minimax-m2.7": {"index": None, "url": None},
    "meta/muse-glimmer-30b": {"index": None, "url": None},  # 10/08/2026 — sem score
}


def aa_to_stars(score: int | float | None) -> int | None:
    """5★ ≥50 | 4★ ≥35 | 3★ ≥20 | 2★ ≥10 | 1★ <10 | None se input None."""
    if score is None:
        return None
    if score >= 50:
        return 5
    if score >= 35:
        return 4
    if score >= 20:
        return 3
    if score >= 10:
        return 2
    return 1


def aa_url_for(model_id: str) -> str | None:
    """Gera URL plausível para AA dado o ID do modelo.

    AA usa slug kebab-case sem vendor prefix, ex:
        nvidia/nemotron-3-super-120b-a12b  →  nvidia-nemotron-3-super-120b-a12b
        deepseek-ai/deepseek-v4-flash     →  deepseek-v4-flash
    """
    if model_id in AA_INTELLIGENCE_INDEX:
        return AA_INTELLIGENCE_INDEX[model_id]["url"]
    # Slug heurístico: remove vendor prefix quando bate com padroes conhecidos
    slug = model_id.replace("/", "-")
    return f"{AA_BASE}{slug}"


def enrich_models_with_aa(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adiciona aa_index, aa_stars e aa_url a cada modelo (se disponível).

    Args:
        models: Lista de modelos (dict) retornada por filter_frontier_models
                ou manualmente curada. Cada dict deve ter chave "id".

    Returns:
        Mesma lista (não é copiada), com aa_index/aa_stars/aa_url adicionados.
    """
    for m in models:
        model_id = m.get("id", "")
        entry = AA_INTELLIGENCE_INDEX.get(model_id)
        if entry:
            m["aa_index"] = entry["index"]
            m["aa_stars"] = aa_to_stars(entry["index"])
            m["aa_url"] = entry["url"]
            # Use display_name if available (e.g., for versioned models)
            if "display_name" in entry:
                m["display_name"] = entry["display_name"]
        else:
            m["aa_index"] = None
            m["aa_stars"] = None
            m["aa_url"] = aa_url_for(model_id)
    return models


def aa_count(models: list[dict[str, Any]]) -> int:
    """Retorna quantos modelos têm AA Index oficial."""
    return sum(1 for m in models if m.get("aa_index") is not None)


if __name__ == "__main__":
    from nim_pipeline.fetch import fetch_nvidia_models
    from nim_pipeline.filter import filter_frontier_models

    raw = fetch_nvidia_models(use_cache=True)
    frontier = filter_frontier_models(raw)
    enriched = enrich_models_with_aa(frontier)
    print(f"Enriquecidos: {len(enriched)} modelos, {aa_count(enriched)} com AA Index")
    print()
    print(f"{'Modelo':<48} {'AA':<5} {'★':<6}")
    for m in sorted(enriched, key=lambda x: -(x.get("aa_index") or 0)):
        aa = m.get("aa_index")
        stars = m.get("aa_stars")
        print(f"{m['id']:<48} {str(aa):<5} {('★' * stars + '☆' * (5 - stars)) if stars else 'N/D':<6}")
