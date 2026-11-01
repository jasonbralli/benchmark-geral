"""
benchmark_pipe.catalog
======================

Catalogos LIVE dos providers — fonte primária de LISTAGEM e de PREÇO.

Problema que este módulo resolve (auditoria 01/11/2026):

Antes, o pipeline usava o cache do Hermes (`provider_models_cache.json`)
como única fonte de IDs e tratava Kilo Code, Nous Portal e NVIDIA como
"providers sem metadados" (passthrough). Consequências reais:

  - Modelos novos dos providers NÃO apareciam (o cache do Hermes só é
    atualizado quando o Hermes consulta o provider).
  - Preço NUNCA era herdado no passthrough → `is_free` dependia só do
    sufixo `:free`. Modelos com preço 0 (ex: `reflection/beam-free`,
    `inclusionai/ling-3.1-flash-1019-free`) ficavam com `is_free=False`
    e sumiam do filtro "só FREE".
  - Sem preço, o CxB usava `price_in or 0.0` → todo modelo pago de
    Kilo/Nous pontuava como se fosse FREE (custo 0 no denominador).

Cada provider tem seu endpoint público de catálogo:

  kilocode  https://api.kilo.ai/api/gateway/models      (384 modelos, pricing)
  nous      https://inference-api.nousresearch.com/v1/models (378 modelos, pricing)
  nvidia    https://integrate.api.nvidia.com/v1/models  (85 IDs, sem ctx)

Todos respondem sem autenticação. O `is_free` passa a ser derivado do
PREÇO REAL do provider (0/0 => free), e não de heurística de sufixo.

Cada catálogo é cacheado em `data/<provider>_models_raw.json`; em falha
de rede usa-se o cache stale (graceful, nunca levanta).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

KILO_API = "https://api.kilo.ai/api/gateway/models"
NOUS_API = "https://inference-api.nousresearch.com/v1/models"
NIM_API = "https://integrate.api.nvidia.com/v1/models"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"

# provider -> (url, cache)
PROVIDER_ENDPOINTS: dict[str, tuple[str, Path]] = {
    "kilocode": (KILO_API, DATA_DIR / "kilo_models_raw.json"),
    "nous": (NOUS_API, DATA_DIR / "nous_models_raw.json"),
    "nvidia-nim": (NIM_API, DATA_DIR / "nim_models_raw.json"),
    # Rota alternativa de MEDIÇÃO (liveness). Cache próprio para não
    # colidir com o cache do map_source (mesmo formato, escrita separada).
    "openrouter": (OPENROUTER_API, DATA_DIR / "openrouter_liveness_raw.json"),
}


def _fetch_json(url: str, timeout: int = 30) -> Any:
    req = Request(url, headers={"User-Agent": "benchmark-geral/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_catalog(provider: str, use_cache: bool = False, timeout: int = 30) -> list[dict[str, Any]]:
    """Baixa o catálogo live de um provider. Retorna lista de dicts.

    Args:
        provider: chave em PROVIDER_ENDPOINTS ("kilocode", "nous", "nvidia-nim").
        use_cache: se True, lê apenas do cache local (sem rede).
        timeout: timeout HTTP em segundos.

    Returns:
        Lista de modelos (dict). Vazia em falha irrecuperável (nunca levanta).
    """
    if provider not in PROVIDER_ENDPOINTS:
        raise KeyError(f"provider sem endpoint live: {provider!r}")
    url, cache = PROVIDER_ENDPOINTS[provider]

    if use_cache and cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("cache %s ilegível (%s)", cache, e)

    try:
        payload = _fetch_json(url, timeout=timeout)
    except (URLError, HTTPError, json.JSONDecodeError, OSError, ValueError) as e:
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    logger.warning("%s falhou (%s) — usando cache stale", provider, e)
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        logger.warning("%s indisponível (%s) — segue sem catálogo live", provider, e)
        return []

    items = payload.get("data") if isinstance(payload, dict) else payload
    items = [i for i in (items or []) if isinstance(i, dict)]

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("cache %s não gravado: %s", cache, e)

    logger.info("catálogo live %s: %d modelos", provider, len(items))
    return items


def fetch_all(use_cache: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Baixa todos os catálogos live. Retorna {provider: [itens]}."""
    out: dict[str, list[dict[str, Any]]] = {}
    for provider in PROVIDER_ENDPOINTS:
        out[provider] = fetch_catalog(provider, use_cache=use_cache)
    return out


def catalog_ids(items: list[dict[str, Any]]) -> set[str]:
    """Extrai o conjunto de model_ids de um catálogo live."""
    return {
        str(i["id"]).strip()
        for i in items
        if isinstance(i, dict) and i.get("id")
    }


def is_zero_priced(item: dict[str, Any]) -> bool:
    """True se o item do catálogo live tem preço 0/0 (=> free real)."""
    pricing = (item or {}).get("pricing") or {}
    try:
        pin = float(pricing.get("prompt", "nan"))
        pout = float(pricing.get("completion", "nan"))
    except (TypeError, ValueError):
        return False
    return pin == 0.0 and pout == 0.0


__all__ = [
    "PROVIDER_ENDPOINTS",
    "KILO_API",
    "NOUS_API",
    "NIM_API",
    "OPENROUTER_API",
    "fetch_catalog",
    "fetch_all",
    "catalog_ids",
    "is_zero_priced",
]
