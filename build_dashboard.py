#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orquestrador: regenera dashboard.html a partir do pipeline nim_pipeline.

Fluxo:
    1. fetch_nvidia_models()          → inventário bruto (cache: data/nvidia_models_raw.json)
    2. filter_frontier_models()       → aplica critério Opção A (23 modelos S+A)
    3. enrich_models_with_aa()        → adiciona AA Index + estrelas calibradas
    4. parse_scorecard()              → top 10 por AA Index (do MD curado humano)
    5. Monta payload JSON + injeta no template dashboard.html

Uso:
    python build_dashboard.py             # usa cache + MD
    python build_dashboard.py --refresh    # re-baixa inventário do models.dev
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Adiciona raiz do projeto ao sys.path para que nim_pipeline seja importável
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from nim_pipeline.fetch import fetch_nvidia_models
from nim_pipeline.filter import filter_frontier_models
from nim_pipeline.enrich import enrich_models_with_aa, aa_count

SRC = BASE / "MODELOS_NVIDIA_NIM_RANKING.md"
TEMPLATE = BASE / "template.html"   # canônico com marker //NIM_RANKING_DATA//
OUT = BASE / "dashboard.html"

# Tier heurístico (gerado pelo filtro) → label exibido no dashboard
TIER_LABELS = {
    "S": "Tier S — Frontier",
    "A": "Tier A — Strong",
}

# Campos por tier nas tabelas
TIER_CONFIG = {
    "S": ["rank", "modelo", "context", "release", "reasoning", "notas"],
    "A": ["rank", "modelo", "context", "release", "reasoning", "notas"],
}

SCORECARD_FIELDS = ["aa_rank", "modelo", "aa_index_raw", "aa_stars_raw", "tier"]

# Artificial Analysis calibration
AA_CALIBRATION = "5★ ≥50 | 4★ ≥35 | 3★ ≥20 | 2★ ≥10 | 1★ <10"

logger = logging.getLogger(__name__)


# ──────────────────────── Markdown parsing ─────────────────────────

def split_row(line: str) -> list[str]:
    """Divide uma linha de tabela MD em células."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_separator(line: str) -> bool:
    """Linha de tabela MD que só tem ---|---|---."""
    return bool(re.match(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", line))


def normalize_model_key(model_str: str) -> str:
    """Remove backticks, parênteses de alias e marcadores de ênfase (*)."""
    # Remove TODOS os backticks (não só os de borda) para lidar com alias
    s = model_str.replace("`", "")
    # Remove *(alias: ...)* e outros itálicos com parênteses
    s = re.sub(r"\s*\*?\([^)]*\)\*?\s*", "", s)
    # Remove asteriscos de itálico/negrito remanescentes
    s = s.replace("*", "").strip()
    return s


# ──────────────────────── Pipeline tier tables ──────────────────────

def tier_tables_from_pipeline(frontier: list[dict[str, Any]]) -> dict[str, list[dict]]:
    """Constrói as tabelas por tier a partir do output do filter.

    Cada tier contém dicts com: rank, modelo, context, release, reasoning, notas,
    aa_index, aa_stars, aa_url.
    """
    by_tier: dict[str, list[dict]] = {"S": [], "A": []}
    rank_counter: dict[str, int] = {"S": 0, "A": 0}

    for m in frontier:
        tier = m.get("tier_heuristic", "A")
        rank_counter[tier] = rank_counter.get(tier, 0) + 1

        ctx = (m.get("limit") or {}).get("context", 0)
        ctx_label = format_context(ctx)
        release = m.get("release_date", "—")
        reasoning = "✓ reasoning" if m.get("reasoning") else "—"
        multimodal = "✓ multimodal" if m.get("attachment") else ""
        open_weights = "open" if m.get("open_weights") else "proprietário"

        notes_parts = [open_weights]
        if multimodal:
            notes_parts.append(multimodal)
        if m.get("tool_call"):
            notes_parts.append("tool-call")

        # AA stars quando disponível
        if m.get("aa_stars"):
            notes_parts.append(f"AA {m['aa_index']}/100")

        by_tier[tier].append({
            "rank": str(rank_counter[tier]),
            "modelo": f"`{m.get('display_name', m['id'])}`",
            "context": ctx_label,
            "release": release,
            "reasoning": reasoning,
            "notas": ", ".join(notes_parts),
            "aa_index": m.get("aa_index"),
            "aa_stars": m.get("aa_stars"),
            "aa_url": m.get("aa_url"),
        })

    return by_tier


def format_context(ctx: int) -> str:
    """Formata context window em K/M."""
    if ctx >= 1_000_000:
        return f"{ctx / 1_000_000:.0f}M" if ctx % 1_000_000 == 0 else f"{ctx / 1_000_000:.1f}M"
    if ctx >= 1024:
        return f"{ctx // 1024}K"
    return str(ctx)


# ──────────────────────── Scorecard from MD ─────────────────────────

def parse_scorecard(text: str) -> list[dict]:
    """Extrai tabela 'Scorecard — Top 10 por AA Index' do MD.

    O scorecard é curado humano (reordenado por AA Index real) e vive no MD.
    O dashboard usa essa tabela para o top 10 mesmo quando o filtro automático
    detecta mais/menos modelos.

    Retorna dicts com chaves: aa_rank (int ou None), modelo (str com backticks),
    aa_index (int ou None), aa_stars (int ou None), tier (str).
    """
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

        # Parse aa_index_raw (string "51" ou "N/D") -> int ou None
        aa_idx_raw = cells[2].strip() if len(cells) > 2 else ""
        if aa_idx_raw.upper() == "N/D" or not aa_idx_raw:
            aa_idx = None
        else:
            try:
                aa_idx = int(aa_idx_raw)
            except ValueError:
                aa_idx = None

        # Parse aa_stars_raw (string "★★★★★" ou "N/D") -> int ou None
        aa_stars_raw = cells[3].strip() if len(cells) > 3 else ""
        if aa_stars_raw.upper() == "N/D" or not aa_stars_raw:
            aa_stars = None
        else:
            aa_stars = aa_stars_raw.count("★")

        corresp = {
            "aa_rank": None,  # será preenchido por compute_aa_ranks
            "modelo": cells[1].strip() if len(cells) > 1 else "",
            "aa_index": aa_idx,
            "aa_stars": aa_stars,
            "tier": cells[4].strip() if len(cells) > 4 else "",
        }
        rows.append(corresp)
        if len(rows) >= 10:
            break
    return rows


# ──────────────────────── aa_rank computation ────────────────────────

def compute_aa_ranks(
    tiers: dict[str, list[dict]],
    scorecard: list[dict],
) -> None:
    """Calcula aa_rank (rank por AA Index) em todos os itens.

    Mutates tiers e scorecard in-place.
    """
    # Coleta todos os modelos com aa_index
    all_aa: list[tuple[Any, str]] = []
    for tier_models in tiers.values():
        for m in tier_models:
            if m.get("aa_index") is not None:
                all_aa.append((m["aa_index"], normalize_model_key(m["modelo"])))
    all_aa.sort(key=lambda x: x[0], reverse=True)

    rank_map = {}
    for rank, (score, key) in enumerate(all_aa, 1):
        rank_map[key] = rank

    # Aplica em tiers
    for tier_models in tiers.values():
        for m in tier_models:
            key = normalize_model_key(m["modelo"])
            m["aa_rank"] = rank_map.get(key)

    # Aplica em scorecard
    for r in scorecard:
        key = normalize_model_key(r["modelo"])
        r["aa_rank"] = rank_map.get(key)

    # Enriquece scorecard com tier via lookup em tiers
    tier_lookup: dict[str, str] = {}
    for tier_key, tier_models in tiers.items():
        for m in tier_models:
            tier_lookup[normalize_model_key(m["modelo"])] = tier_key

    for r in scorecard:
        key = normalize_model_key(r["modelo"])
        r["tier"] = tier_lookup.get(key, "")


# ──────────────────────── Payload assembly ──────────────────────────

def assemble_payload(
    text: str,
    frontier: list[dict],
    tiers: dict[str, list[dict]],
    scorecard: list[dict],
) -> dict[str, Any]:
    today = datetime.now().strftime("%d/%m/%Y")
    total = sum(len(v) for v in tiers.values())
    aa_total = aa_count(frontier)

    return {
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


# ──────────────────────── Main ──────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Regenera dashboard.html")
    parser.add_argument(
        "--refresh", action="store_true",
        help="Re-busca inventário do models.dev (ignora cache)"
    )
    parser.add_argument(
        "--use-cache", action="store_true",
        help="Usa cache mesmo se existir (default: fetch se cache ausente)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Log detalhado"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # 1. Fetch
    raw = fetch_nvidia_models(use_cache=args.use_cache and not args.refresh)

    # 2. Filter (critério Opção A)
    frontier = filter_frontier_models(raw)

    # 3. Enrich com AA
    frontier = enrich_models_with_aa(frontier)

    # 4. Constrói tabelas por tier a partir do filtro
    tiers = tier_tables_from_pipeline(frontier)

    # 5. Scorecard do MD (curado humano)
    if SRC.exists():
        text = SRC.read_text(encoding="utf-8")
        scorecard = parse_scorecard(text)
    else:
        logger.warning(f"MD nao encontrado: {SRC}. Scorecard vazio.")
        scorecard = []

    # 6. Calcula aa_rank cross-tier
    compute_aa_ranks(tiers, scorecard)

    # 7. Monta payload
    payload = assemble_payload(text, frontier, tiers, scorecard)

    # 8. Injeta no template (canônico) e escreve dashboard.html
    if not TEMPLATE.exists():
        raise SystemExit(f"Template nao encontrado: {TEMPLATE}")
    html_tmpl = TEMPLATE.read_text(encoding="utf-8")
    marker = "//NIM_RANKING_DATA//"
    if marker not in html_tmpl:
        raise SystemExit(f"Marker '{marker}' nao encontrado no template.")

    # Substitui marker pelo JSON
    new_html = html_tmpl.replace(marker, json.dumps(payload, ensure_ascii=False))
    OUT.write_text(new_html, encoding="utf-8")

    # 9. Relatório
    total = sum(len(v) for v in tiers.values())
    logger.info(f"Dashboard gerado: {OUT}")
    logger.info(f"  Inventario bruto: {len(raw)} modelos")
    logger.info(f"  Filtrados (Opcao A): {len(frontier)} modelos")
    logger.info(f"  Tier S: {len(tiers['S'])} | Tier A: {len(tiers['A'])}")
    logger.info(f"  Com AA Index: {aa_count(frontier)}")
    logger.info(f"  Scorecard: {len(scorecard)} itens")


if __name__ == "__main__":
    main()
