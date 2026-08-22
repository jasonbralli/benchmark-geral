"""benchmark_pipe.normalize
==========================

Schema unificado (UnifiedModel) + derive_is_free + normalizadores por provider.

7 formatos de fonte -> 1 schema. Adapters desmontam o dict bruto de cada
fonte (models.dev, openrouter) em campos comuns:

    provider, model_id, display_name, context_k, tool_call, reasoning,
    multimodal, open_weights, price_in, price_out, is_free, aa_index,
    cxb_score, source, release_date

Regra is_free (resolve "free sem tag" vs "tag free"):
    - providers 100% grátis por política (nvidia, opencode-free) -> True
    - model_id termina em ":free" -> True
    - price_in == price_out == 0 (com price_in não-None) -> True
    - demais -> False
"""

from __future__ import annotations

import math  # noqa: F401  (mantido para compat se score circular importar)
from dataclasses import dataclass, field, asdict
from typing import Any

ALL_FREE_PROVIDERS = frozenset({"nvidia", "opencode-free"})


@dataclass
class UnifiedModel:
    provider: str
    model_id: str
    display_name: str | None = None
    context_k: int | None = None
    tool_call: bool | None = None
    reasoning: bool | None = None
    multimodal: bool = False
    open_weights: bool | None = None
    price_in: float | None = None      # USD / 1M tokens input
    price_out: float | None = None     # USD / 1M tokens output
    is_free: bool = False
    aa_index: float | None = None
    cxb_score: float = 0.0
    source: str = "unknown"
    release_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["display_name"] is None:
            d["display_name"] = self.model_id
        return d


def derive_is_free(
    provider: str,
    model_id: str,
    price_in: float | None,
    price_out: float | None,
) -> bool:
    """Resolve 'free' sem depender de tag do provider."""
    if provider in ALL_FREE_PROVIDERS:
        return True
    if model_id.endswith(":free"):
        return True
    if price_in is not None and price_in == 0 and price_out == 0:
        return True
    return False


def is_rankable(m: UnifiedModel) -> bool:
    """Entra no ranking CxB? Exige dado de capacidade real (ctx OU tool_call).

    aa_index NÃO habilita ranking sozinho — providers passthrough (gemini/
    kilocode/huggingface/nous/opencode-free) só têm AA curado, sem ctx/toolcall/
    pricing, e devem ficar no inventário N/D fora do rank (decisão de escopo).
    AA soma ao benefit apenas para quem já é rankável por capacidade.
    """
    return m.context_k is not None or m.tool_call is not None


# ---------------------------------------------------------------------------
# Normalizadores por provider
# ---------------------------------------------------------------------------

def normalize_nvidia(items: list[dict[str, Any]]) -> list[UnifiedModel]:
    """models.dev -> UnifiedModel (provider=nvidia)."""
    out: list[UnifiedModel] = []
    for m in items:
        model_id = m.get("id") or ""
        if not model_id:
            continue
        limit = m.get("limit") or {}
        ctx = limit.get("context")
        cost = m.get("cost") or {}
        price_in = cost.get("input")
        price_out = cost.get("output")
        mods = m.get("modalities") or {}
        multimodal = bool(m.get("attachment")) or "image" in (mods.get("input") or [])
        um = UnifiedModel(
            provider="nvidia",
            model_id=model_id,
            display_name=m.get("display_name") or m.get("name") or model_id,
            context_k=(ctx // 1024) if isinstance(ctx, int) else None,
            tool_call=bool(m["tool_call"]) if "tool_call" in m else None,
            reasoning=bool(m["reasoning"]) if "reasoning" in m else None,
            multimodal=multimodal,
            open_weights=m.get("open_weights"),
            price_in=price_in,
            price_out=price_out,
            is_free=False,  # set abaixo
            source="models.dev",
            release_date=m.get("release_date"),
        )
        um.is_free = derive_is_free("nvidia", model_id, price_in, price_out)
        out.append(um)
    return out


def _usd_per_million(tok_price: str | float | None) -> float | None:
    """OpenRouter devolve preço por TOKEN (string). Converte para USD/1M."""
    if tok_price is None:
        return None
    try:
        v = float(tok_price)
    except (TypeError, ValueError):
        return None
    return round(v * 1_000_000, 6)


def normalize_openrouter(items: list[dict[str, Any]]) -> list[UnifiedModel]:
    """openrouter.ai/api/v1/models -> UnifiedModel."""
    out: list[UnifiedModel] = []
    for m in items:
        model_id = m.get("id") or ""
        if not model_id:
            continue
        pricing = m.get("pricing") or {}
        price_in = _usd_per_million(pricing.get("prompt"))
        price_out = _usd_per_million(pricing.get("completion"))
        ctx = m.get("context_length")
        um = UnifiedModel(
            provider="openrouter",
            model_id=model_id,
            display_name=m.get("name") or model_id,
            context_k=(int(ctx) // 1024) if isinstance(ctx, (int, float)) else None,
            tool_call=None,   # OpenRouter não expõe flag confiável neste endpoint
            reasoning=None,
            multimodal=False,
            open_weights=None,
            price_in=price_in,
            price_out=price_out,
            is_free=False,  # set abaixo
            source="openrouter-api",
            release_date=None,
        )
        um.is_free = derive_is_free("openrouter", model_id, price_in, price_out)
        out.append(um)
    return out


def passthrough_ids(provider: str, ids: set[str] | list[str]) -> list[UnifiedModel]:
    """Providers sem fonte de metadados: gera entries N/D (visíveis, não drop)."""
    out: list[UnifiedModel] = []
    for mid in sorted(set(ids)):
        um = UnifiedModel(
            provider=provider,
            model_id=mid,
            display_name=mid,
            source="hermes-cache-only",
        )
        um.is_free = derive_is_free(provider, mid, None, None)
        out.append(um)
    return out
