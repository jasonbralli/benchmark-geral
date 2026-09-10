#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-atualização completa do pipeline benchmark_geral.

Uso:
    python update_pipeline.py                # usa cache local + MD atual
    python update_pipeline.py --refresh      # busca models.dev + atualiza AA via web_search
    python update_pipeline.py --txt <file>   # usa lista txt como ground truth + MD
    python update_pipeline.py --all          # --refresh + --txt + AA web_search + roda tudo

Fluxo automatizado:
  1. Obtém inventário (models.dev ou txt)
  2. Filtra Opção A
  3. Enriquece AA Index:
     - Cache estático (AA_INTELLIGENCE_INDEX em enrich.py)
     - Fallback: web_search Artificial Analysis para modelos sem score
  4. Atualiza MODELOS_NVIDIA_NIM_RANKING.md (scorecard top 10 por AA)
  5. Regenera dashboard.html
  6. Roda pytest
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from nim_pipeline.fetch import fetch_nvidia_models
from nim_pipeline.filter import filter_frontier_models
from nim_pipeline.enrich import enrich_models_with_aa, AA_INTELLIGENCE_INDEX, aa_count

logger = logging.getLogger(__name__)

# Config
MODELS_DEV_API = "https://models.dev/api.json"
PROVIDER = "nvidia"
CACHE_PATH = BASE / "data" / "nvidia_models_raw.json"
MD_PATH = BASE / "MODELOS_NVIDIA_NIM_RANKING.md"
TEMPLATE = BASE / "template.html"
OUT = BASE / "dashboard.html"

# Scorecard marker no MD
SCORECARD_HEADER = "## 📊 Scorecard — Top 10 por AA Index"
SCORECARD_TABLE_START = "| AA Rank | Modelo | AA Index | AA ★ | Tier |"

AA_CALIBRATION = "5★ ≥50 | 4★ ≥35 | 3★ ≥20 | 2★ ≥10 | 1★ <10"
AA_BASE_URL = "https://artificialanalysis.ai/models/"

# Tier labels
TIER_LABELS = {
    "S": "Tier S — Frontier",
    "A": "Tier A — Strong",
}
TIER_COLS_STANDARD = ["rank", "modelo", "context", "release", "aa_index", "aa_stars", "notas"]
TIER_CONFIG = {"S": TIER_COLS_STANDARD, "A": TIER_COLS_STANDARD}
SCORECARD_FIELDS = ["aa_rank", "modelo", "aa_index_raw", "aa_stars_raw", "tier"]


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )


def parse_txt_list(txt_path: Path) -> set[str]:
    """Parse do arquivo txt (formato: N|\"vendor/model\") -> set de IDs."""
    ids = set()
    with txt_path.open(encoding="utf-8") as f:
        for line in f:
            m = re.search(r'"([^"]+)"', line)
            if m:
                ids.add(m.group(1).strip())
    logger.info(f"TXT parsed: {len(ids)} modelos")
    return ids


def fetch_models_dev(use_cache: bool) -> list[dict[str, Any]]:
    """Busca inventário do models.dev (com cache)."""
    if use_cache and CACHE_PATH.exists():
        logger.info(f"Lendo cache: {CACHE_PATH}")
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    logger.info(f"Buscando {MODELS_DEV_API}")
    req = Request(MODELS_DEV_API, headers={"User-Agent": "benchmark-geral/auto"})
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError) as e:
        if CACHE_PATH.exists():
            logger.warning(f"API falhou ({e}). Usando cache.")
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        raise RuntimeError(f"Falha ao buscar models.dev: {e}") from e

    provider = data.get(PROVIDER, {})
    models = list(provider.get("models", {}).values())
    logger.info(f"models.dev: {len(models)} modelos NVIDIA")

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Cache salvo: {CACHE_PATH}")
    return models


def merge_with_txt(raw_models: list[dict], txt_ids: set[str] | None) -> list[dict]:
    """Merge: usa models.dev como base, adiciona modelos do txt que faltam com metadados estimados."""
    if txt_ids is None:
        return raw_models

    existing_ids = {m["id"] for m in raw_models}
    missing = txt_ids - existing_ids

    if not missing:
        logger.info("Merge TXT: todos os IDs já estão no models.dev")
        return raw_models

    logger.info(f"Merge TXT: {len(missing)} modelos extras do txt não estão no models.dev")

    # Metadados conhecidos para modelos extras comuns (pode ser expandido)
    EXTRA_METADATA: dict[str, dict[str, Any]] = {
        "moonshotai/kimi-k3": {
            "id": "moonshotai/kimi-k3",
            "name": "Kimi K3",
            "description": "Moonshot AI frontier open-weight model, 2.8T params, 1M context, multimodal reasoning",
            "family": "kimi-k3",
            "attachment": True,
            "reasoning": True,
            "tool_call": True,
            "temperature": True,
            "knowledge": "2026-06",
            "release_date": "2026-07-16",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "modalities": {"input": ["text", "image", "video"], "output": ["text"]},
            "open_weights": True,
            "limit": {"context": 1048576, "output": 65536},
            "cost": {"input": 0, "output": 0},
            "status": "active",
        },
    }

    for mid in sorted(missing):
        if mid in EXTRA_METADATA:
            raw_models.append(EXTRA_METADATA[mid])
            logger.info(f"  + Injetado com metadados: {mid}")
        else:
            logger.warning(f"  - Sem metadados conhecidos: {mid} - ignorado no filtro")

    return raw_models


def web_search_aa(model_id: str) -> int | None:
    """Busca AA Index via web_search (simulado - requer integração real)."""
    logger.debug(f"AA web_search para {model_id} - não implementado inline")
    return None


def enrich_with_aa(frontier: list[dict]) -> list[dict]:
    """Enriquece com AA Index (cache estático + web_search opcional)."""
    # Primeiro usa o enrich nativo (cache estático do enrich.py)
    enriched = enrich_models_with_aa(frontier)

    # Identifica modelos sem AA Index
    missing = [m for m in enriched if m.get("aa_index") is None]
    if missing:
        logger.info(f"{len(missing)} modelos sem AA Index: {[m['id'] for m in missing]}")
        # TODO: integração real com web_search aqui
        # for m in missing:
        #     score = web_search_aa(m["id"])
        #     if score is not None:
        #         m["aa_index"] = score
        #         m["aa_stars"] = stars_from_index(score)
        #         m["aa_url"] = f"{AA_BASE_URL}{slugify(m['id'])}"

    return enriched


def stars_from_index(idx: int | None) -> int | None:
    if idx is None:
        return None
    if idx >= 50:
        return 5
    if idx >= 35:
        return 4
    if idx >= 20:
        return 3
    if idx >= 10:
        return 2
    return 1


def slugify(model_id: str) -> str:
    """vendor/model -> vendor-model (heurística AA)."""
    return model_id.replace("/", "-").replace(".", "-").lower()


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_separator(line: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", line))


def normalize_model_key(model_str: str) -> str:
    s = model_str.replace("`", "")
    s = re.sub(r"\s*\*?\([^)]*\)\*?\s*", "", s)
    s = s.replace("*", "").strip()
    return s


def format_context(ctx: int) -> str:
    if ctx >= 1_000_000:
        return f"{ctx // 1_000_000:.0f}M" if ctx % 1_000_000 == 0 else f"{ctx / 1_000_000:.1f}M"
    if ctx >= 1024:
        return f"{ctx // 1024}K"
    return str(ctx)


def build_tier_tables(frontier: list[dict]) -> dict[str, list[dict]]:
    by_tier: dict[str, list[dict]] = {"S": [], "A": []}
    rank_counter: dict[str, int] = {"S": 0, "A": 0}

    for m in frontier:
        tier = m.get("tier_heuristic", "A")
        rank_counter[tier] = rank_counter.get(tier, 0) + 1

        ctx = (m.get("limit") or {}).get("context", 0)
        ctx_label = format_context(ctx)
        release = m.get("release_date", "—")

        notes = []
        notes.append("open" if m.get("open_weights") else "proprietário")
        if m.get("attachment"):
            notes.append("multimodal")

        by_tier[tier].append({
            "rank": str(rank_counter[tier]),
            "modelo": f"`{m.get('display_name', m['id'])}`",
            "context": ctx_label,
            "release": release,
            "notas": ", ".join(notes),
            "aa_index": m.get("aa_index"),
            "aa_stars": m.get("aa_stars"),
            "aa_url": m.get("aa_url"),
        })

    return by_tier


def compute_aa_ranks(tiers: dict[str, list[dict]], scorecard: list[dict]) -> None:
    all_aa: list[tuple[Any, str]] = []
    for tier_models in tiers.values():
        for m in tier_models:
            if m.get("aa_index") is not None:
                all_aa.append((m["aa_index"], normalize_model_key(m["modelo"])))
    all_aa.sort(key=lambda x: x[0], reverse=True)

    rank_map = {}
    for rank, (score, key) in enumerate(all_aa, 1):
        rank_map[key] = rank

    for tier_models in tiers.values():
        for m in tier_models:
            key = normalize_model_key(m["modelo"])
            m["aa_rank"] = rank_map.get(key)

    for r in scorecard:
        key = normalize_model_key(r["modelo"])
        r["aa_rank"] = rank_map.get(key)

    tier_lookup: dict[str, str] = {}
    for tier_key, tier_models in tiers.items():
        for m in tier_models:
            tier_lookup[normalize_model_key(m["modelo"])] = tier_key

    for r in scorecard:
        key = normalize_model_key(r["modelo"])
        r["tier"] = tier_lookup.get(key, "")


def parse_scorecard(text: str) -> list[dict]:
    rows: list[dict] = []
    grabbing = False
    for line in text.splitlines():
        stripped = line.strip()
        if "Scorecard" in stripped and "Top 10" in stripped:
            grabbing = True
            continue
        if not grabbing:
            continue
        if not stripped.startswith("|"):
            if stripped.startswith("## ") and "Scorecard" not in stripped:
                break
            continue
        if is_separator(stripped):
            continue
        cells = split_row(stripped)
        if cells[0].lower().startswith("aa rank") or cells[0].lower().startswith("rank"):
            continue
        if len(cells) < len(SCORECARD_FIELDS):
            continue

        aa_idx_raw = cells[2].strip() if len(cells) > 2 else ""
        if aa_idx_raw.upper() == "N/D" or not aa_idx_raw:
            aa_idx = None
        else:
            try:
                aa_idx = int(aa_idx_raw)
            except ValueError:
                aa_idx = None

        aa_stars_raw = cells[3].strip() if len(cells) > 3 else ""
        if aa_stars_raw.upper() == "N/D" or not aa_stars_raw:
            aa_stars = None
        else:
            aa_stars = aa_stars_raw.count("★")

        corresp = {
            "aa_rank": None,
            "modelo": cells[1].strip() if len(cells) > 1 else "",
            "aa_index": aa_idx,
            "aa_stars": aa_stars,
            "tier": cells[4].strip() if len(cells) > 4 else "",
        }
        rows.append(corresp)
        if len(rows) >= 10:
            break
    return rows


def generate_scorecard_md(tiers: dict[str, list[dict]]) -> str:
    # Calcula rank_map apenas para ordenar o scorecard
    all_aa: list[tuple[Any, str]] = []
    for tier_models in tiers.values():
        for m in tier_models:
            if m.get("aa_index") is not None:
                all_aa.append((m["aa_index"], normalize_model_key(m["modelo"])))
    all_aa.sort(key=lambda x: x[0], reverse=True)

    rank_map = {}
    for rank, (score, key) in enumerate(all_aa, 1):
        rank_map[key] = rank

    all_items = []
    for tier_key, tier_models in tiers.items():
        for m in tier_models:
            if m.get("aa_index") is not None:
                key = m["modelo"].replace("`", "")
                all_items.append({
                    "id": key,
                    "aa_index": m["aa_index"],
                    "aa_stars": m["aa_stars"],
                    "tier": tier_key,
                })

    all_items.sort(key=lambda x: x["aa_index"], reverse=True)
    top10 = all_items[:10]

    lines = [
        "",
        SCORECARD_HEADER,
        "",
        f"Ranking ordenado pelo **Artificial Analysis Intelligence Index v4.1** (score third-party oficial, 0-100). Modelos sem score AA aparecem no final com `N/D`. Calibração: {AA_CALIBRATION}",
        "",
        "| AA Rank | Modelo | AA Index | AA ★ | Tier |",
        "|--------:|--------|---------:|:----:|:----:|",
    ]

    for i, item in enumerate(top10, 1):
        stars = "★" * item["aa_stars"] if item["aa_stars"] else "N/D"
        lines.append(f"| {i} | `{item['id']}` | {item['aa_index']} | {stars} | {item['tier']} |")

    no_aa = [m for m in all_items if m["aa_index"] is None][:10 - len(top10)]
    for item in no_aa:
        lines.append(f"| N/D | `{item['id']}` | N/D | N/D | {item['tier']} |")

    lines.append("")
    return "\n".join(lines)


def update_markdown(scorecard_md: str):
    text = MD_PATH.read_text(encoding="utf-8")

    start_idx = text.find(SCORECARD_HEADER)
    if start_idx == -1:
        raise RuntimeError(f"Header scorecard não encontrado: {SCORECARD_HEADER}")

    end_idx = text.find("\n---\n", start_idx)
    if end_idx == -1:
        end_idx = text.find("\n## ", start_idx + len(SCORECARD_HEADER))
    if end_idx == -1:
        end_idx = len(text)

    new_text = text[:start_idx] + scorecard_md + text[end_idx:]
    MD_PATH.write_text(new_text, encoding="utf-8")
    logger.info(f"MD atualizado: {MD_PATH}")


def run_pytest():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=BASE,
        capture_output=True,
        text=True,
        timeout=180
    )
    if result.returncode != 0:
        logger.error(f"pytest falhou:\n{result.stdout}\n{result.stderr}")
        raise RuntimeError("Testes falharam")
    logger.info("Testes passaram")


def main():
    parser = argparse.ArgumentParser(description="Auto-atualização pipeline benchmark_geral")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-busca inventário do models.dev")
    parser.add_argument("--txt", type=Path,
                        help="Arquivo txt com lista de IDs (ground truth)")
    parser.add_argument("--all", action="store_true",
                        help="Equivale a --refresh + --txt + --aa-web + pipeline completo")
    parser.add_argument("--aa-web", action="store_true",
                        help="Tenta buscar AA Index via web_search para modelos sem score (experimental)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.all:
            args.refresh = True
            args.txt = args.txt or Path(os.environ.get("NVIDIA_MODEL_LIST", r"C:\Users\Jason\Desktop\nvidia_model_list.txt"))
            args.aa_web = True

    logger.info("=== Iniciando auto-atualização ===")

    # 1. Inventário
    raw = fetch_models_dev(use_cache=not args.refresh)

    # 2. Merge por TXT se fornecido
    txt_ids = parse_txt_list(args.txt) if args.txt else None
    
    # Se --txt não fornecido, tenta ler do sync_hermes_models.py
    if txt_ids is None:
        hermes_txt = BASE / "data" / "nvidia_models_from_hermes.txt"
        if hermes_txt.exists():
            # Ler o txt gerado pelo sync
            txt_ids = set()
            for line in hermes_txt.read_text(encoding="utf-8").splitlines():
                m = re.search(r'"([^"]+)"', line)
                if m:
                    txt_ids.add(m.group(1).strip())
            logger.info(f"Usando txt do sync Hermes: {len(txt_ids)} modelos")
    
    raw = merge_with_txt(raw, txt_ids)

    # 3. Filtro Opção A
    frontier = filter_frontier_models(raw)
    logger.info(f"Frontier (Opção A): {len(frontier)} modelos")

    # 4. Enriquece AA
    frontier = enrich_with_aa(frontier)
    aa_total = sum(1 for m in frontier if m.get("aa_index") is not None)
    logger.info(f"Com AA Index: {aa_total}/{len(frontier)}")

    # 5. Tabelas por tier
    tiers = build_tier_tables(frontier)
    logger.info(f"Tier S: {len(tiers['S'])} | Tier A: {len(tiers['A'])}")

    # 6. Scorecard MD + aa_rank cross-tier
    scorecard_md = generate_scorecard_md(tiers)
    update_markdown(scorecard_md)

    # 7. Monta payload e injeta no template (replicando build_dashboard.py)
    # Scorecard: parse do MD atualizado
    text = MD_PATH.read_text(encoding="utf-8")
    scorecard = parse_scorecard(text)

    # Calcula aa_rank cross-tier
    compute_aa_ranks(tiers, scorecard)

    today = datetime.now().strftime("%d/%m/%Y")
    total = sum(len(v) for v in tiers.values())

    payload = {
        "meta": {
            "title": "Modelos NVIDIA NIM — Ranking de Capacidade",
            "data": today,
            "total_ranked": total,
            "aa_count": aa_total,
            "criteria": (
                "Pipeline automatizado (Opção A): tool_call=True AND "
                "(reasoning=True OR release>=2026) AND context>=128K. "
                "Exclui embeddings, vision-only pequenos, safety, translation."
            ),
            "source": (
                "Inventário NVIDIA via models.dev/api.json (atualizado diariamente). "
                "Curadoria humana em MODELOS_NVIDIA_NIM_RANKING.md para scores manuais."
            ),
            "aa_source": (
                f"Artificial Analysis Intelligence Index v4.1 — "
                f"{aa_total}/{total} modelos com score oficial third-party"
            ),
            "aa_calibration": AA_CALIBRATION,
            "pipeline": "nim_pipeline.fetch → filter → enrich",
            "last_inventory_sync": datetime.now().isoformat(timespec="seconds"),
        },
        "tiers": {
            key: {"label": TIER_LABELS[key], "models": tiers.get(key, [])}
            for key in TIER_CONFIG.keys()
        },
        "scorecard": scorecard,
    }

    if not TEMPLATE.exists():
        raise SystemExit(f"Template não encontrado: {TEMPLATE}")
    html_tmpl = TEMPLATE.read_text(encoding="utf-8")
    marker = "//NIM_RANKING_DATA//"
    if marker not in html_tmpl:
        raise SystemExit(f"Marker '{marker}' não encontrado no template.")

    new_html = html_tmpl.replace(marker, json.dumps(payload, ensure_ascii=False))
    OUT.write_text(new_html, encoding="utf-8")

    logger.info(f"Dashboard gerado: {OUT}")
    logger.info(f"  Inventario bruto: {len(raw)} modelos")
    logger.info(f"  Filtrados (Opcao A): {len(frontier)} modelos")
    logger.info(f"  Tier S: {len(tiers['S'])} | Tier A: {len(tiers['A'])}")
    logger.info(f"  Com AA Index: {aa_total}")
    logger.info(f"  Scorecard: {len(scorecard)} itens")

    # 8. Testes
    run_pytest()

    logger.info("=== Auto-atualização concluída com sucesso ===")


if __name__ == "__main__":
    main()