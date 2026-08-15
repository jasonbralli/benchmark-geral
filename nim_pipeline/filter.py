"""
nim_pipeline.filter
===================

Aplica o critério de filtragem **Opção A — Estrito** sobre o inventário bruto
de modelos NVIDIA.

Critério:
    tool_call=True            (essencial para agentic)
    AND (
        reasoning=True
        OR release_date >= "2026-01-01"
    )
    AND limit.context >= 131072 (128K)
    AND não está em EXCLUDE_FAMILIES

EXCLUDE_FAMILIES: famílias de modelos que não são LLMs de chat/instruct
generais (embeddings, content safety, retrieval, rerank, specialized vision,
protein folding, translation, etc).

Cada modelo que passa recebe um campo `tier` sugerido ("S" ou "A") baseado em
heurísticas simples sobre contexto, multimodalidade, reasoning e recência.
A confirmação final do Tier (com estrelas manuais ou AA index) é feita em
enrich.py.

Uso:
    from nim_pipeline.filter import filter_frontier_models
    frontier = filter_frontier_models(raw_models)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

MIN_CONTEXT = 131072  # 128K
RECENT_RELEASE = "2026-01-01"
VINTAGE_RELEASE = "2025-07-01"

# Famílias / padrões que não são LLMs chat/instruct gerais
EXCLUDE_FAMILIES = frozenset([
    "embed", "rerank", "retrieval", "retrieve", "guard", "safety",
    "nemotron-content-safety", "nemotron-3-content-safety",
    "cosmos-predict", "cosmos-transfer", "cosmos-reason",
    "gliner", "studiovoice", "magpie-tts", "voicechat",
    "usdcode", "usdvalidate", "riva-translate", "whisper",
    "esm2", "esmfold", "paligemma", "sparsedrive", "streampetr",
    "active-speaker-detection", "bevformer", "synthetic-video-detector",
    "dracarys", "solar", "mistral-7b-instruct",
])


def _parse_date(s: str | None) -> datetime | None:
    """Parse seguro de datas YYYY-MM-DD (YYYY-MM tratado como YYYY-MM-01)."""
    if not s:
        return None
    s = s.strip()
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", s)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else 1
    day = int(m.group(3)) if m.group(3) else 1
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def is_excluded(model: dict[str, Any]) -> bool:
    """Retorna True se modelo deve ser excluído por família/categoria."""
    family = (model.get("family") or "").lower()
    model_id = model.get("id", "").lower()
    name = model.get("name", "").lower()
    description = model.get("description", "").lower()

    blob = f"{family}|{model_id}|{name}|{description}"

    # Excluir se familia/id bater em EXCLUDE_FAMILIES
    for ex in EXCLUDE_FAMILIES:
        if ex in blob:
            return True

    # Excluir vision-only sem capacidade de texto (attachment-only puro)
    mods = model.get("modalities", {})
    if "text" not in mods.get("input", []) or "text" not in mods.get("output", []):
        return True

    # Excluir modelos com nome de família claramente specialist
    specialist_markers = [
        "embedding", "embed", "vision-language model",
        "image classification", "object detection",
    ]
    for marker in specialist_markers:
        if marker in description:
            return True

    return False


def _is_recent_or_reasoning(model: dict[str, Any]) -> bool:
    if model.get("reasoning"):
        return True
    release = _parse_date(model.get("release_date"))
    if release and release >= datetime.fromisoformat(RECENT_RELEASE):
        return True
    return False


def _context_ok(model: dict[str, Any]) -> bool:
    limit = model.get("limit", {}) or {}
    ctx = limit.get("context")
    return ctx is not None and ctx >= MIN_CONTEXT


def _tool_call_ok(model: dict[str, Any]) -> bool:
    return bool(model.get("tool_call"))


def _heuristic_tier(model: dict[str, Any]) -> str:
    """Heurística simples para sugerir S ou A (confirmado depois no enrich)."""
    score = 0
    if model.get("reasoning"):
        score += 3
    if model.get("open_weights"):
        score += 1
    limit = model.get("limit", {}) or {}
    if limit.get("context", 0) >= 524288:  # 512K
        score += 2
    elif limit.get("context", 0) >= 262144:  # 256K
        score += 1
    release = _parse_date(model.get("release_date"))
    if release and release >= datetime.fromisoformat("2026-06-01"):
        score += 2
    elif release and release >= datetime.fromisoformat("2026-01-01"):
        score += 1
    if model.get("attachment"):  # multimodal
        score += 1
    if model.get("structured_output"):
        score += 1
    # Modelos S típicos: score >= 7
    return "S" if score >= 7 else "A"


def filter_frontier_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aplica critério Opção A e retorna apenas modelos qualificados.

    Cada modelo retornado inclui o campo `tier_heuristic` ("S" ou "A") e
    `passes_filter` (lista de checks que passou).
    """
    qualified: list[dict[str, Any]] = []
    for m in models:
        if is_excluded(m):
            continue
        if not _tool_call_ok(m):
            continue
        if not _is_recent_or_reasoning(m):
            continue
        if not _context_ok(m):
            continue

        # Decora com tier heurístico e auditoria
        m_copy = dict(m)
        m_copy["tier_heuristic"] = _heuristic_tier(m)
        qualified.append(m_copy)

    # Ordena por heurística (S primeiro) e depois por contexto desc
    qualified.sort(
        key=lambda x: (
            0 if x["tier_heuristic"] == "S" else 1,
            -((x.get("limit") or {}).get("context") or 0),
            x["id"],
        )
    )
    return qualified


def filter_by_tier(
    models: list[dict[str, Any]], tier: str
) -> list[dict[str, Any]]:
    """Filtra modelos pelo tier heurístico ('S' ou 'A')."""
    return [m for m in models if m.get("tier_heuristic") == tier]


if __name__ == "__main__":
    from nim_pipeline.fetch import fetch_nvidia_models
    raw = fetch_nvidia_models(use_cache=True)
    frontier = filter_frontier_models(raw)
    print(f"Filtrados: {len(frontier)}/{len(raw)} modelos")
    print()
    print("Tier S:")
    for m in filter_by_tier(frontier, "S"):
        print(f"  {m['id']:50s} ctx={(m.get('limit') or {}).get('context', 0) // 1024}K")
    print()
    print("Tier A:")
    for m in filter_by_tier(frontier, "A"):
        print(f"  {m['id']:50s} ctx={(m.get('limit') or {}).get('context', 0) // 1024}K")
