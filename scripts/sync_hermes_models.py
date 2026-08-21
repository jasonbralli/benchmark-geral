#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_hermes_models.py
=====================
Monitora o cache de modelos do Hermes (provider_models_cache.json) e sincroniza
novos modelos NVIDIA relevantes com o pipeline de benchmark.

Lógica:
  1. Lê cache Hermes (todos providers)
  2. Extrai modelos nvidia/* (ignora :free, :batch, quantizações -BF16/-NVFP4)
  3. Compara com data/nvidia_models_raw.json
  4. Adiciona novos com metadados estimados
  5. Opcional: salva snapshot do cache para diff futuro

Uso:
    python sync_hermes_models.py              # detecta novos e adiciona
    python sync_hermes_models.py --dry-run    # só mostra o que seria adicionado
    python sync_hermes_models.py --all        # inclui :free/quantizações (não recomendado)
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# Config
HERMES_CACHE = Path(r"C:\Users\Jason\AppData\Local\hermes\provider_models_cache.json")
SNAPSHOT_PATH = BASE / "data" / "hermes_models_snapshot.json"
PIPELINE_CACHE = BASE / "data" / "nvidia_models_raw.json"
TXT_OUTPUT = BASE / "data" / "nvidia_models_from_hermes.txt"

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def load_hermes_cache() -> dict[str, set[str]]:
    """Lê cache Hermes e retorna {provider: set(models)}."""
    if not HERMES_CACHE.exists():
        logger.warning(f"Cache Hermes não encontrado: {HERMES_CACHE}")
        return {}

    cache = json.loads(HERMES_CACHE.read_text(encoding="utf-8"))
    result = {}
    for provider, data in cache.items():
        result[provider] = set(data.get("models", []))
    logger.info(f"Cache Hermes: {len(cache)} providers")
    for p, ms in result.items():
        logger.debug(f"  {p}: {len(ms)} modelos")
    return result


def extract_relevant_models(hermes_cache: dict[str, set[str]]) -> set[str]:
    """Extrai modelos relevantes do cache Hermes.
    
    Foco: apenas provider 'nvidia' (que reflete o catálogo NIM direto).
    Os outros providers (openrouter, kilocode) agregam de várias fontes pagas,
    não representando o que está disponível no NIM.
    """
    relevant = set()
    
    # Apenas NVIDIA - único provider que reflete catálogo NIM
    for provider, models in hermes_cache.items():
        if provider != "nvidia":
            continue
        for m in models:
            # Ignora variantes :free/:batch
            if ":" in m:
                continue
            relevant.add(m)
    
    logger.info(f"Total modelos NVIDIA no cache Hermes: {len(relevant)}")
    return relevant


def is_variant(model_id: str) -> bool:
    """Verifica se é variante (quantização, :free, :batch, etc)."""
    lower = model_id.lower()
    # :free, :batch, :exp, etc
    if ":" in model_id:
        return True
    # -BF16, -NVFP4, etc
    if re.search(r"-(bf16|nvfp4|fp8|int8|int4)$", lower):
        return True
    # -VL, -Vision, -Vision-Instruct
    if "-vl" in lower or "vision" in lower:
        return True
    return False


def is_specialized(model_id: str) -> bool:
    """Verifica se é modelo especializado (embed, guard, safety, etc)."""
    lower = model_id.lower()
    special_patterns = [
        "embed", "guard", "safety", "retriev", "rerank", "parse",
        "translate", "clip", "neva", "vila", "chatqa", "reward",
        "ising", "usdc", "usdval", "studiovoice", "magpie", "tts",
        "whisper", "speech", "asr", "nemo", "cosmos", "bev",
        "synthetic", "detector", "active-speaker", "gliner",
        "paligemma", "esm", "deplot", "fuyu", "kosmos", "sea-lion",
        "starcoder", "codegemma", "codestral", "codellama",
        "recurrentgemma", "mistral-nemo-minitron", "nemotron-mini",
        "nemotron-nano", "nemotron-3-nano", "nemotron-4-340b",
        "palmyra",
    ]
    return any(p in lower for p in special_patterns)


def classify_new_models(new_models: set[str]) -> dict[str, list[str]]:
    """Classifica novos modelos em: frontier, specialized, variants."""
    result = {"frontier": [], "specialized": [], "variants": []}
    for m in sorted(new_models):
        if is_variant(m):
            result["variants"].append(m)
        elif is_specialized(m):
            result["specialized"].append(m)
        else:
            result["frontier"].append(m)
    return result


def is_nim_relevant(model_id: str) -> bool:
    """Verifica se modelo é relevante para o benchmark NIM.
    
    Regras:
    1. Está no catálogo NVIDIA NIM (nvidia/*)
    2. OU é frontier conhecido (claude, gpt, gemini, etc) com tool_call
    3. NÃO é especializado (embed, guard, etc)
    """
    m = model_id.lower()
    
    # NVIDIA NIM direto
    if m.startswith("nvidia/"):
        return not is_specialized(model_id)
    
    # Frontier de outros vendors (para comparação no ranking)
    frontier_vendors = [
        "anthropic/claude", "openai/gpt", "google/gemini",
        "deepseek", "moonshotai", "minimax", "z-ai", "qwen",
        "stepfun", "poolside", "thinkingmachines", "x-ai",
        "bytedance", "tencent", "meta/llama", "mistralai",
    ]
    
    for vendor in frontier_vendors:
        if m.startswith(vendor):
            return not is_specialized(model_id)
    
    return False


def load_pipeline_cache() -> list[dict[str, Any]]:
    if not PIPELINE_CACHE.exists():
        logger.warning(f"Cache pipeline não encontrado: {PIPELINE_CACHE}")
        return []
    return json.loads(PIPELINE_CACHE.read_text(encoding="utf-8"))


def save_pipeline_cache(models: list[dict[str, Any]]):
    PIPELINE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_CACHE.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Cache pipeline salvo: {len(models)} modelos")


def generate_txt_output(models: set[str]):
    """Gera arquivo txt no formato da lista manual."""
    lines = []
    for i, m in enumerate(sorted(models), 1):
        lines.append(f'{i}|"{m}"')
    TXT_OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"TXT gerado: {TXT_OUTPUT} ({len(lines)} modelos)")


def save_snapshot(models: set[str]):
    SNAPSHOT_PATH.write_text(json.dumps(sorted(models), indent=2), encoding="utf-8")
    logger.info(f"Snapshot salvo: {SNAPSHOT_PATH}")


def load_snapshot() -> set[str]:
    if not SNAPSHOT_PATH.exists():
        return set()
    return set(json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8")))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sincroniza modelos NVIDIA do Hermes com pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Só mostra, não modifica")
    parser.add_argument("--all", action="store_true", help="Inclui variantes (:free, quantizações)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    logger.info("=== Sincronização Hermes → Pipeline ===")

    # 1. Carrega caches
    hermes = load_hermes_cache()
    if not hermes:
        logger.error("Cache Hermes vazio ou não encontrado")
        return

    nvidia_hermes = extract_relevant_models(hermes)

    # 2. Classifica
    if not args.all:
        nvidia_hermes = {m for m in nvidia_hermes if not is_variant(m)}
        logger.info(f"Após remover variantes: {len(nvidia_hermes)}")
    
    # Filtra apenas modelos NIM-relevantes (NVIDIA ou frontier comparável)
    nvidia_hermes = {m for m in nvidia_hermes if is_nim_relevant(m)}
    logger.info(f"NIM-relevantes (NVIDIA + frontier comparável): {len(nvidia_hermes)}")

    # 3. Compara com pipeline
    pipeline = load_pipeline_cache()
    pipeline_ids = {m["id"] for m in pipeline}

    new_models = nvidia_hermes - pipeline_ids
    existing = nvidia_hermes & pipeline_ids

    logger.info(f"\nJá no pipeline: {len(existing)}")
    logger.info(f"Novos detectados: {len(new_models)}")

    if new_models:
        classified = classify_new_models(new_models)
        
        logger.info(f"\n--- Classificação dos novos ---")
        logger.info(f"Frontier (chat/instruct general): {len(classified['frontier'])}")
        for m in classified["frontier"]:
            logger.info(f"  + {m}")
        
        logger.info(f"Specialized (embed/guard/etc): {len(classified['specialized'])}")
        for m in classified["specialized"]:
            logger.info(f"  ~ {m}")
        
        logger.info(f"Variants (quantização/:free): {len(classified['variants'])}")
        for m in classified["variants"]:
            logger.debug(f"  = {m}")

        # 4. Gera saída
        if not args.dry_run:
            # Gera txt com TUDO (para referência)
            generate_txt_output(nvidia_hermes)
            
            # Salva snapshot
            save_snapshot(nvidia_hermes)
            
            # Adiciona ao pipeline se for frontier
            if classified["frontier"]:
                logger.info(f"\nAdicionando {len(classified['frontier'])} modelos frontier ao pipeline...")
                # Aqui você integraria com update_pipeline.py
                # Por ora, apenas logamos a ação
                for m in classified["frontier"]:
                    logger.info(f"  → {m} (metadados estimados necessários em EXTRA_METADATA)")
    else:
        logger.info("\nNenhum modelo novo detectado")

    # 5. Compara com snapshot anterior
    prev_snapshot = load_snapshot()
    if prev_snapshot != nvidia_hermes:
        diff_added = nvidia_hermes - prev_snapshot
        diff_removed = prev_snapshot - nvidia_hermes
        logger.info(f"\n--- Mudanças vs snapshot anterior ---")
        logger.info(f"Adicionados: {len(diff_added)}")
        for m in sorted(diff_added):
            logger.info(f"  + {m}")
        logger.info(f"Removidos: {len(diff_removed)}")
        for m in sorted(diff_removed):
            logger.info(f"  - {m}")
    else:
        logger.info("\nSem mudanças vs snapshot anterior")

    logger.info("\n=== Sincronização concluída ===")


if __name__ == "__main__":
    main()