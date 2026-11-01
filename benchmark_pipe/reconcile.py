"""
benchmark_pipe.reconcile
========================

Guarda de PARIDADE entre o catálogo live de cada provider e o que o
dashboard realmente exibiu.

Por que existe: em 01/11/2026 a auditoria do benchmark-geral encontrou
modelos que o provider já listava mas que NÃO apareciam no dashboard
(Mistral Large 4 no NVIDIA, Ornith 1.5 122B no Nous) e modelos com
preço 0 que NÃO entravam no filtro "só FREE" (Beam 1.0 e Ling 3.1 Flash
1019 no Kilo). A causa era sempre a mesma: a listagem vinha de um cache
secundário e o preço nunca era conferido contra a fonte real.

Este módulo roda no fim de TODA curadoria diária e responde:

  - `missing`       IDs que o provider lista e o dashboard NÃO mostrou
  - `free_mismatch` IDs com preço 0 que o dashboard não marcou FREE
  - `extra`         IDs que o dashboard mostrou e o provider já removeu

O relatório é gravado em `data/catalog_parity.json` e lido pelo
`curate_daily.py`, que transforma as divergências em alerta no Telegram.
É o mecanismo que impede o problema de voltar a acontecer silenciosamente.
"""

from __future__ import annotations

import logging
from typing import Any

from .catalog import catalog_ids, is_zero_priced

logger = logging.getLogger(__name__)

# provider do dashboard -> chave do catálogo live correspondente
LIVE_KEY_BY_PROVIDER: dict[str, str] = {
    "kilocode": "kilocode",
    "nous": "nous",
    "nvidia": "nvidia-nim",
}

# Remove sufixos de variante (:free / -free) para comparar IDs que se referem
# ao mesmo modelo lógico com formas de gravação distintas (ex.:
# dashboard guarda "ornith/ornith-1.5-122b" e o catálogo live usa
# "ornith/ornith-1.5-122b:free").
import re as _re

_VARIANT_RE = _re.compile(r"(:free|-free)$", _re.I)

def strip_model_id(mid: str) -> str:
    """ID normalizado para comparação: minúsculo, sem sufixo de variante."""
    return _VARIANT_RE.sub("", mid.lower().strip())

def _shown_set(models: list[Any]) -> tuple[set[str], set[str]]:
    """IDs exibidos (incluindo aliases) e os marcados FREE, forma normalizada."""
    ids: set[str] = set()
    free: set[str] = set()
    for m in models:
        mid = getattr(m, "model_id", None) or ""
        ids.add(strip_model_id(mid))
        for alias in getattr(m, "aliases", []) or []:
            ids.add(strip_model_id(alias))
        if getattr(m, "is_free", False):
            free.add(strip_model_id(mid))
    return ids, free

def reconcile(
    models: list[Any],
    live_catalogs: dict[str, list[dict[str, Any]]],
    hermes_inventory: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Compara o dashboard com os catálogos live.

    Args:
        models: lista de UnifiedModel (o que foi construído para o dashboard).
        live_catalogs: {chave_live: [itens]} — ver `catalog.fetch_all`.

    Returns:
        dict com as chaves `missing`, `free_mismatch`, `extra` e `by_provider`.
    """
    by_provider: dict[str, dict[str, Any]] = {}

    for provider, live_key in LIVE_KEY_BY_PROVIDER.items():
        items = live_catalogs.get(live_key) or []
        live_ids = {strip_model_id(str(i["id"])) for i in items if isinstance(i, dict) and i.get("id")}
        live_free = {
            strip_model_id(str(i["id"]))
            for i in items
            if isinstance(i, dict) and i.get("id") and is_zero_priced(i)
        }

        shown = [m for m in models if getattr(m, "provider", None) == provider]
        shown_ids, shown_free = _shown_set(shown)

        # missing: modelos que estão no catálogo live E (quando houver
        # inventário) no inventário Hermes, mas não foram exibidos.
        if hermes_inventory is not None:
            inv_ids = {strip_model_id(m) for m in hermes_inventory.get(provider, set())}
            missing_candidates = live_ids & inv_ids
        else:
            missing_candidates = live_ids
        missing = sorted(mid for mid in missing_candidates if mid not in shown_ids)

        free_mismatch = sorted(live_free - shown_free)
        extra = sorted(shown_ids - live_ids)

        by_provider[provider] = {
            "missing": missing,
            "free_mismatch": free_mismatch,
            "extra": extra,
            "live_total": len(live_ids),
            "shown_total": len(shown_ids),
            "live_free_total": len(live_free),
            "shown_free_total": len(shown_free),
        }

    total_missing = sum(len(v["missing"]) for v in by_provider.values())
    total_free = sum(len(v["free_mismatch"]) for v in by_provider.values())
    total_extra = sum(len(v["extra"]) for v in by_provider.values())

    report = {
        "missing": total_missing,
        "free_mismatch": total_free,
        "extra": total_extra,
        "by_provider": by_provider,
    }
    logger.info(
        "paridade: missing=%d free_mismatch=%d extra=%d", total_missing, total_free, total_extra
    )
    return report


def format_report(report: dict[str, Any], max_items: int = 6) -> list[str]:
    """Formata o relatório de paridade em linhas curtas para alerta."""
    lines: list[str] = []
    for provider, data in sorted((report.get("by_provider") or {}).items()):
        missing = data.get("missing") or []
        free_mismatch = data.get("free_mismatch") or []
        extra = data.get("extra") or []
        if missing:
            sample = ", ".join(missing[:max_items])
            more = f" (+{len(missing) - max_items})" if len(missing) > max_items else ""
            lines.append(f"📋 {provider}: {len(missing)} do provider sem display — {sample}{more}")
        if free_mismatch:
            sample = ", ".join(free_mismatch[:max_items])
            more = f" (+{len(free_mismatch) - max_items})" if len(free_mismatch) > max_items else ""
            lines.append(f"🏷️ {provider}: {len(free_mismatch)} com preço 0 fora do filtro FREE — {sample}{more}")
        if extra:
            lines.append(f"🗑️ {provider}: {len(extra)} exibidos e removidos pelo provider")
    return lines


__all__ = ["reconcile", "format_report", "LIVE_KEY_BY_PROVIDER"]
