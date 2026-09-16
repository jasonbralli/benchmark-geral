"""benchmark_pipe.aa_api
========================
Fetch bulk da Artificial Analysis Data API v2 (Free tier) para enriquecer
o aa_index do CXB. Design enxuto:

- 1 endpoint paginado: GET /api/v2/language/models/free?page=N&page_size=200
- Cache em data/aa_models_raw.json com TTL 24h (= janela de quota Free)
- Graceful fallback: sem key / 401/403/429 / offline -> usa cache stale ou dict curado
- Mapping flexível: slug AA (kebab, sem vendor) -> index, com heurística
  para casar com canonical_id (ex: z-ai/glm-5.2 <-> glm-5-2, nvidia/nemotron-3-super-120b-a12b <-> nvidia-nemotron-3-super-120b-a12b)

Env:
  AA_API_KEY_benchmark_geral  (preferido) ou AA_API_KEY genérico
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

AA_FREE_URL = "https://artificialanalysis.ai/api/v2/language/models/free"
CACHE = Path(__file__).parent.parent / "data" / "aa_models_raw.json"
TTL_HOURS = 24


def _cache_is_fresh(path: Path = CACHE, ttl_hours: int = TTL_HOURS) -> bool:
    if not path.exists():
        return False
    try:
        age_s = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        return age_s < ttl_hours * 3600
    except OSError:
        return False


def _get_api_key() -> str | None:
    for k in ("AA_API_KEY_benchmark_geral", "AA_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY"):
        v = os.environ.get(k)
        if v:
            return v.strip()
    # tenta .env local
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            kk, vv = line.split("=", 1)
            kk = kk.strip()
            if kk in ("AA_API_KEY_benchmark_geral", "AA_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY"):
                vv = vv.strip().strip('"').strip("'")
                if vv:
                    return vv
    return None


def fetch_aa_models(
    api_key: str | None = None,
    use_cache: bool = True,
    ttl_hours: int = TTL_HOURS,
    cache_path: Path = CACHE,
) -> dict[str, Any] | None:
    """Busca bulk paginado da AA Free. Retorna payload {version, fetched_at, data} ou None se fallback."""
    if use_cache and _cache_is_fresh(cache_path, ttl_hours):
        logger.info("AA cache fresco: %s", cache_path)
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("AA cache ilegível: %s", e)

    key = api_key or _get_api_key()
    if not key:
        logger.info("AA_API_KEY ausente — usando fallback curado")
        return None

    all_data: list[dict[str, Any]] = []
    version: Any = None
    page = 1
    try:
        while True:
            url = f"{AA_FREE_URL}?page={page}&page_size=200"
            req = Request(url, headers={"x-api-key": key, "User-Agent": "benchmark-geral/1.0"})
            with urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                if version is None:
                    version = payload.get("intelligence_index_version")
                chunk = payload.get("data", [])
                all_data.extend(chunk)
                pag = payload.get("pagination", {})
                has_more = pag.get("has_more", False)
                # log rate limit
                rem = resp.headers.get("X-Ratelimit-Remaining")
                logger.info("AA page %d: %d itens has_more=%s remaining=%s", page, len(chunk), has_more, rem)
                if not has_more:
                    break
                page += 1
                if page > 10:
                    logger.warning("AA paginação excedeu 10 páginas — interrompendo")
                    break
    except HTTPError as e:
        if e.code in (401, 403, 429):
            logger.warning("AA %s — fallback curado (quota/auth). Body: %s", e.code, e.read().decode()[:500] if hasattr(e, "read") else "")
            # tenta cache stale mesmo que expirado
            if cache_path.exists():
                try:
                    logger.info("Usando AA cache stale: %s", cache_path)
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return None
        logger.warning("AA HTTPError %s: %s", e.code, e)
        return None
    except (URLError, OSError, json.JSONDecodeError, ValueError) as e:
        logger.warning("AA fetch falhou (%s) — fallback curado", e)
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    out = {
        "intelligence_index_version": version,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total": len(all_data),
        "data": all_data,
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("AA cache salvo: %s (%d modelos, v%s)", cache_path, len(all_data), version)
    except OSError as e:
        logger.warning("Falha ao salvar AA cache: %s", e)
    return out


def _norm_slug(s: str) -> str:
    """Normaliza slug/model part para comparação: lower, '.'->'-', '_'->'-', collapse '--'."""
    s = s.lower().strip().lstrip("~").replace("`", "")
    s = s.replace(".", "-").replace("_", "-")
    s = re.sub(r"-{2,}", "-", s)
    return s


def build_aa_index_map(raw: dict[str, Any] | list[dict[str, Any]]) -> dict[str, float]:
    """Constrói {slug_norm: index} a partir do payload AA. Mantém maior index se slug duplicado (max effort)."""
    data = raw["data"] if isinstance(raw, dict) and "data" in raw else raw  # type: ignore
    if not isinstance(data, list):
        return {}
    out: dict[str, float] = {}
    for m in data:
        slug = (m.get("slug") or "").strip()
        if not slug:
            continue
        idx = None
        ev = m.get("evaluations") or {}
        idx = ev.get("artificial_analysis_intelligence_index")
        if idx is None:
            # free shape may have null for not measured
            continue
        try:
            idx_f = float(idx)
        except (TypeError, ValueError):
            continue
        key = _norm_slug(slug)
        # keep max if duplicate slug appears (e.g., gpt-oss variants are distinct slugs, not dups)
        if key not in out or idx_f > out[key]:
            out[key] = idx_f
        # also index full vendor hyphenated variants are already slug, so no extra key needed
    return out


def _f(v: Any) -> float | None:
    """Converte para float tolerante; None/<invalido> -> None."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_aa_metrics_map(
    raw: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, float | None]]:
    """Mapa rico {slug_norm: {aa_index, speed_tps, ttft_s, e2e_s, coding_index, agentic_index}}.

    Mesma heurística de chave de build_aa_index_map. Mantém a entrada com MAIOR
    aa_index quando slug duplica (mas preserva métricas de quem perde se forem
    as únicas disponíveis e o vencedor tiver None).
    """
    data = raw["data"] if isinstance(raw, dict) and "data" in raw else raw  # type: ignore
    if not isinstance(data, list):
        return {}
    out: dict[str, dict[str, float | None]] = {}
    for m in data:
        slug = (m.get("slug") or "").strip()
        if not slug:
            continue
        ev = m.get("evaluations") or {}
        perf = m.get("performance") or {}
        entry: dict[str, float | None] = {
            "aa_index": _f(ev.get("artificial_analysis_intelligence_index")),
            "coding_index": _f(ev.get("artificial_analysis_coding_index")),
            "agentic_index": _f(ev.get("artificial_analysis_agentic_index")),
            "speed_tps": _f(perf.get("median_output_tokens_per_second")),
            "ttft_s": _f(perf.get("median_time_to_first_token_seconds")),
            "e2e_s": _f(perf.get("median_end_to_end_response_time_seconds")),
        }
        key = _norm_slug(slug)
        if key not in out:
            out[key] = entry
            continue
        # merge: prefer entry de maior aa_index; propaga métricas se faltam lá
        cur = out[key]
        cur_idx = cur.get("aa_index")
        new_idx = entry.get("aa_index")
        if new_idx is not None and (cur_idx is None or new_idx > cur_idx):
            merged = dict(entry)
            for k, v in cur.items():
                if merged.get(k) is None:
                    merged[k] = v
            out[key] = merged
        else:
            for k, v in entry.items():
                if cur.get(k) is None and v is not None:
                    cur[k] = v
    return out


def lookup_aa_metrics(
    model_id: str,
    canonical_id: str | None,
    metrics_map: dict[str, dict[str, float | None]],
) -> dict[str, float | None] | None:
    """Mesma estratégia de lookup_aa_index, mas retorna o dict de métricas completo."""
    if not metrics_map:
        return None
    # Reusa lookup index para achar a chave que casa
    idx_map = {k: v["aa_index"] for k, v in metrics_map.items() if v.get("aa_index") is not None}
    if not idx_map:
        return None
    found_idx = lookup_aa_index(model_id, canonical_id, idx_map)
    if found_idx is None:
        return None
    # Recupera a chave cuja aa_index casa (pode haver >1; pega a de maior score)
    for key, metrics in metrics_map.items():
        if metrics.get("aa_index") == found_idx:
            return metrics
    return None


def lookup_aa_index(
    model_id: str,
    canonical_id: str | None,
    aa_map: dict[str, float],
) -> float | None:
    """Tenta casar model_id/canonical com o mapa AA slug->index. Retorna index ou None."""
    if not aa_map:
        return None
    candidates: list[str] = []
    for raw in [model_id, canonical_id or ""]:
        if not raw:
            continue
        low = raw.lower().strip()
        # derivar partes
        last = low.split("/")[-1]  # ex: kimi-k3, glm-5.2
        full_hyphen = low.replace("/", "-").replace(".", "-").replace("_", "-")
        last_norm = _norm_slug(last)
        full_norm = _norm_slug(full_hyphen)
        # ordem: last_norm primeiro (AA frequentemente omite vendor), depois full_norm
        for c in (last_norm, full_norm, _norm_slug(low)):
            if c and c not in candidates:
                candidates.append(c)
        # também tentar sem sufixo de variante de modelo AA (ex: -low, -non-reasoning) via prefix match
        # não adiciona aqui, mas no lookup final faz substring fallback
    # 1) match exato
    for c in candidates:
        if c in aa_map:
            return aa_map[c]
    # 2) fallback: slug é prefixo do candidate ou vice-versa (lida com deepseek-v4-flash-0731 vs deepseek-v4-flash)
    #    escolhe o de maior score entre os que casam por prefixo
    best: tuple[float, str] | None = None
    for c in candidates:
        for slug, idx in aa_map.items():
            if slug == c or c.startswith(slug + "-") or slug.startswith(c + "-") or c == slug.replace(".", "-"):
                if best is None or idx > best[0]:
                    best = (idx, slug)
    if best:
        return best[0]
    # 3) contains (mais permissivo, último recurso)
    for c in candidates:
        for slug, idx in aa_map.items():
            if slug in c or c in slug:
                if best is None or idx > best[0]:
                    best = (idx, slug)
    if best:
        return best[0]
    return None
