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

Normalização canónica (2026-08-22):
    - canonicalize() resolve aliases de vendor/sufixo de variante para
      agrupar o mesmo modelo lógico (ex: z-ai/glm-5.2:free -> z-ai/glm-5.2)
    - dedup_models() colapsa duplicatas intra-provider (mesmo provider +
      mesmo canónico + mesma variante) preservando aliases/divergences.
"""

from __future__ import annotations

import logging
import math  # noqa: F401  (mantido para compat se score circular importar)
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)

ALL_FREE_PROVIDERS = frozenset({"nvidia", "opencode-free"})

# IDs free do Nous Portal (freeRecommendedModels), populado pelo orquestrador
# via set_nous_free_ids(). Dinâmico: reflete o que o Portal anuncia agora —
# sem hardcode de IDs no pipeline. Contém tanto a forma bare ("tencent/hy3")
# quanto a sufixada ("tencent/hy3:free"), para casar com o que vier do
# provider_models_cache.
_NOUS_FREE_IDS: set[str] = set()


def set_nous_free_ids(ids: set[str] | list[str] | None) -> None:
    """Injeta o conjunto de IDs free vindos do Nous Portal (dinâmico).

    Aceita formas bare e ':free'; armazena ambas para matching tolerante.
    Chamada pelo orquestrador (run_consolidated.py) antes da normalização.
    """
    global _NOUS_FREE_IDS
    out: set[str] = set()
    for mid in ids or []:
        m = str(mid).strip().lower()
        if not m:
            continue
        out.add(m)
        if m.endswith(":free"):
            out.add(m[: -len(":free")])
        else:
            out.add(f"{m}:free")
    _NOUS_FREE_IDS = out

# ---------------------------------------------------------------------------
# Normalização canónica
# ---------------------------------------------------------------------------

VENDOR_ALIAS: dict[str, str] = {
    "deepseek": "deepseek-ai",
    "zai-org": "z-ai",
}

# Modelos lógicos que são o mesmo checkpoint apesar de IDs diferentes.
# Chave e valor em forma já lower + sem sufixo de variante.
CANONICAL_EQUIV: dict[str, str] = {
    "deepseek-ai/deepseek-v4-flash": "deepseek-ai/deepseek-v4-flash-0731",
}

VARIANT_SUFFIXES = (":free", ":batch", ":nitro")


def canonicalize(model_id: str) -> tuple[str, str]:
    """Normaliza model_id -> (canonical_id, variant).

    - lower + strip ` ~
    - detecta variante (:free/:batch/:nitro) sem criar modelo novo
    - aplica VENDOR_ALIAS (deepseek -> deepseek-ai, zai-org -> z-ai)
    - aplica CANONICAL_EQUIV (deepseek-v4-flash -> deepseek-v4-flash-0731)

    Variant retornado: 'free' | 'batch' | 'nitro' | 'base'
    """
    raw = model_id.lower().replace("`", "").strip()
    # strip leading ~ usado por OpenRouter para aliases temporários
    raw = raw.lstrip("~").strip()

    variant = "base"
    base = raw
    for suffix in VARIANT_SUFFIXES:
        if raw.endswith(suffix):
            base = raw[: -len(suffix)]
            variant = suffix[1:]  # sem ':'
            break

    # vendor alias (só antes da barra)
    if "/" in base:
        vendor, rest = base.split("/", 1)
        vendor = VENDOR_ALIAS.get(vendor, vendor)
        base = f"{vendor}/{rest}"

    canonical = CANONICAL_EQUIV.get(base, base)
    return canonical, variant


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
    family: str | None = None            # ex: "nemotron", "llama", "gpt" — filtro granular
    structured_output: bool | None = None  # suporta JSON mode / structured output
    has_cache_pricing: bool | None = None  # cost.cache_read presente (reuso de contexto)
    price_in: float | None = None      # USD / 1M tokens input
    price_out: float | None = None     # USD / 1M tokens output
    is_free: bool = False
    aa_index: float | None = None
    cxb_score: float = 0.0
    source: str = "unknown"
    release_date: str | None = None
    # Normalização canónica
    canonical_id: str | None = None
    variant: str = "base"
    aliases: list[str] = field(default_factory=list)
    divergences: dict[str, list[Any]] = field(default_factory=dict)

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
    if provider == "nous" and model_id.lower() in _NOUS_FREE_IDS:
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


def apply_canonical(m: UnifiedModel) -> UnifiedModel:
    """Preenche canonical_id/variant in-place a partir de m.model_id."""
    canon, var = canonicalize(m.model_id)
    m.canonical_id = canon
    m.variant = var
    return m


def dedup_models(
    models: list[UnifiedModel],
    hermes_inventory: dict[str, set[str]] | None = None,
) -> list[UnifiedModel]:
    """Colapsa duplicatas intra-provider (provider + canonical + variant).

    Preserva verdade da fonte:
    - vencedor guarda aliases = outros model_ids do mesmo grupo
    - vencedor guarda divergences = {campo: [valores distintos]}
    - loga warning para cada colapso (auditoria)

    Heurística de vencedor (ordem de prioridade):
    1. presente em hermes_inventory (fonte de verdade de IDs)
    2. maior context_k
    3. release_date mais recente (ISO string)
    """
    # garante canonical preenchido
    for m in models:
        if m.canonical_id is None:
            apply_canonical(m)

    groups: dict[tuple[str, str, str], list[UnifiedModel]] = defaultdict(list)
    for m in models:
        key = (m.provider, m.canonical_id or "", m.variant)
        groups[key].append(m)

    out: list[UnifiedModel] = []
    for key, grp in groups.items():
        if len(grp) == 1:
            out.append(grp[0])
            continue

        # elege vencedor
        def rank_key(m: UnifiedModel) -> tuple[int, int, str]:
            in_hermes = 0
            if hermes_inventory is not None:
                ids = hermes_inventory.get(m.provider)
                if ids is not None:
                    if m.model_id in ids:
                        in_hermes = 2  # ID exato no inventário — vence
                    elif m.canonical_id in ids:
                        in_hermes = 1  # só o canónico presente (alias)
            ctx = m.context_k or 0
            rel = m.release_date or ""
            return (in_hermes, ctx, rel)

        grp_sorted = sorted(grp, key=rank_key, reverse=True)
        winner = grp_sorted[0]
        losers = grp_sorted[1:]

        winner.aliases = sorted({x.model_id for x in grp if x.model_id != winner.model_id})
        divergences: dict[str, list[Any]] = {}
        # context_k
        ctx_vals = sorted({x.context_k for x in grp if x.context_k is not None})
        if len(ctx_vals) > 1:
            divergences["context_k"] = ctx_vals
        price_in_vals = sorted({x.price_in for x in grp if x.price_in is not None})
        if len(price_in_vals) > 1:
            divergences["price_in"] = price_in_vals
        price_out_vals = sorted({x.price_out for x in grp if x.price_out is not None})
        if len(price_out_vals) > 1:
            divergences["price_out"] = price_out_vals
        # release_date divergente também é útil
        rel_vals = sorted({x.release_date for x in grp if x.release_date})
        if len(rel_vals) > 1:
            divergences["release_date"] = rel_vals
        winner.divergences = divergences

        logger.warning(
            "dedup intra-provider %s canonical=%s variant=%s : %d -> 1 (winner=%s aliases=%s divergences=%s)",
            winner.provider,
            winner.canonical_id,
            winner.variant,
            len(grp),
            winner.model_id,
            winner.aliases,
            divergences,
        )
        # Para não perder metadados: se vencedor tem context None e perdedor tem,
        # não sobrescreve silenciosamente — divergences já registra. Mantém vencedor.
        out.append(winner)

    return out


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
            family=m.get("family"),
            structured_output=(bool(m["structured_output"]) if "structured_output" in m else None),
            has_cache_pricing=True if "cache_read" in (cost or {}) else False,
            price_in=price_in,
            price_out=price_out,
            is_free=False,  # set abaixo
            source="models.dev",
            release_date=m.get("release_date"),
        )
        um.is_free = derive_is_free("nvidia", model_id, price_in, price_out)
        apply_canonical(um)
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


def normalize_openrouter(
    items: list[dict[str, Any]],
    meta_index: dict[str, dict[str, Any]] | None = None,
) -> list[UnifiedModel]:
    """openrouter.ai/api/v1/models -> UnifiedModel.

    Preço vem do payload openrouter-api (real por-provider). Campos funcionais
    (ctx, tool_call, reasoning, open_weights, release) que o endpoint OpenRouter
    não expõe são herdados do cross-join models_dev_cache, quando disponível.
    """
    out: list[UnifiedModel] = []
    for m in items:
        model_id = m.get("id") or ""
        if not model_id:
            continue
        pricing = m.get("pricing") or {}
        price_in = _usd_per_million(pricing.get("prompt"))
        price_out = _usd_per_million(pricing.get("completion"))
        ctx = m.get("context_length")

        # Cross-join: campos funcionais que o endpoint OR não fornece
        # Variantes :free/:batch cruzam com a base canónica (z-ai/glm-5.2:free -> z-ai/glm-5.2)
        lookup_id = model_id
        for suffix in (":free", ":batch", ":nitro"):
            if model_id.endswith(suffix):
                lookup_id = model_id[: -len(suffix)]
                break
        # strip ~ para lookup
        lookup_id = lookup_id.lstrip("~")
        x = (meta_index or {}).get(lookup_id) or {}
        if ctx is None:
            ctx = (x.get("limit") or {}).get("context")
        tool_call = x.get("tool_call")
        reasoning = x.get("reasoning")
        open_weights = x.get("open_weights")
        release_date = x.get("release_date")

        um = UnifiedModel(
            provider="openrouter",
            model_id=model_id,
            display_name=m.get("name") or model_id,
            context_k=(int(ctx) // 1024) if isinstance(ctx, (int, float)) else None,
            tool_call=bool(tool_call) if tool_call is not None else None,
            reasoning=bool(reasoning) if reasoning is not None else None,
            multimodal=False,
            open_weights=open_weights,
            price_in=price_in,
            price_out=price_out,
            is_free=False,  # set abaixo
            source="openrouter-api",
            release_date=release_date,
        )
        um.is_free = derive_is_free("openrouter", model_id, price_in, price_out)
        apply_canonical(um)
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
        apply_canonical(um)
        out.append(um)
    return out


def passthrough_ids_enriched(
    provider: str,
    ids: set[str] | list[str],
    meta_index: dict[str, dict[str, Any]],
) -> list[UnifiedModel]:
    """Passthrough IDs com cross-join de metadados do models_dev_cache.

    FUNCIONAIS (ctx/tool/reasoning/multimodal/weights/release) herdam do
    primeiro provider que expõe cada campo — são propriedades do MODELO.
    PREÇO/IS_FREE NÃO herdam de outro provider: são específicos por provider.
    Sem meta de preço própria -> price None (N/D) e is_free depende só do
    ALL_FREE_PROVIDERS. Evita que kilocode/nous apareçam FREE por herdar o
    custo 0 do nvidia.
    """
    out: list[UnifiedModel] = []
    for mid in sorted(set(ids)):
        meta = meta_index.get(mid)
        if not meta:
            um = UnifiedModel(
                provider=provider,
                model_id=mid,
                display_name=mid,
                source="hermes-cache-only",
            )
            um.is_free = derive_is_free(provider, mid, None, None)
            apply_canonical(um)
            out.append(um)
            continue

        limit = meta.get("limit") or {}
        ctx = limit.get("context")
        mods = meta.get("modalities") or {}
        multimodal = bool(meta.get("attachment")) or "image" in (mods.get("input") or [])
        # Preço NÃO vem do cross-join (seria de outro provider) — fica N/D.
        um = UnifiedModel(
            provider=provider,
            model_id=mid,
            display_name=meta.get("display_name") or meta.get("name") or mid,
            context_k=(ctx // 1024) if isinstance(ctx, int) else None,
            tool_call=bool(meta["tool_call"]) if "tool_call" in meta else None,
            reasoning=bool(meta["reasoning"]) if "reasoning" in meta else None,
            multimodal=multimodal,
            open_weights=meta.get("open_weights"),
            family=meta.get("family"),
            structured_output=(bool(meta["structured_output"]) if "structured_output" in meta else None),
            has_cache_pricing=True if "cache_read" in (meta.get("cost") or {}) else False,
            price_in=None,   # preço é por-provider; N/D aqui
            price_out=None,
            is_free=False,   # set abaixo
            source="models.dev-cross",
            release_date=meta.get("release_date"),
        )
        um.is_free = derive_is_free(provider, mid, None, None)
        apply_canonical(um)
        out.append(um)
    return out
