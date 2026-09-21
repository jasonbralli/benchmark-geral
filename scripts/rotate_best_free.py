"""scripts/rotate_best_free.py
=============================

MONITOR do fallback chain free do Hermes (read-only — NÃO escreve no config).

A rotação é 100% manual (o usuário aplica a chain no config.yaml via UI).
Este script só **monitora e alerta**:

  1. Lê a **chain atual** do `config.yaml` (`fallback_providers:`).
  2. Cruza cada tier com o **health real** (uptime/p50/last_ok) e marca
     tiers com health ruim (⚠️).
  3. Calcula a **recomendação CxB** (top free por CxB, 1 tier por
     provider, SEM filtro de health) para referência — o que a regra de
     curadoria apontaria hoje.
  4. Gera um alerta HTML para o Telegram (enviado pelo curate_daily).

Fontes:
  1. **Curadoria CxB** — `data/consolidated_models.json` (is_free, cxb_score).
  2. **Health real** — `../benchmark_providers/data/provider_health.json`
     (probe diário: uptime 24h, p50, last_ok).
  3. **Config do Hermes** — `fallback_providers:` (chain manual atual).

Uso:
    python scripts/rotate_best_free.py             # JSON (read-only)
    python scripts/rotate_best_free.py --alert     # texto HTML p/ Telegram

Exit codes: 0=ok, 2=falha crítica (config/health ilegível).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# provider_health.json — override via PROVIDERS_DATA_DIR (mesmo contrato do build.py)
PROVIDERS_DATA_DIR = Path(
    os.environ.get("PROVIDERS_DATA_DIR", str(ROOT.parent / "benchmark_providers" / "data"))
)
HEALTH_JSON = PROVIDERS_DATA_DIR / "provider_health.json"
CONSOLIDATED = ROOT / "data" / "consolidated_models.json"
CONFIG_YAML = Path(os.environ.get(
    "HERMES_CONFIG_YAML",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "config.yaml"),
))

DEFAULT_TOP = 7      # tiers exibidos na recomendação CxB (espelha a curadoria manual)
MAX_TIERS = 10
# Uptime abaixo disso (em %) marca o tier com ⚠️ no alerta
LOW_UPTIME_PCT = 50.0

# Providers que NUNCA entram na recomendação (não são "free provider" de verdade
# ou são o primário local).
EXCLUDED_PROVIDERS = {"local-localhost-8080", "copilot-acp", "custom"}


def load_health() -> dict:
    if not HEALTH_JSON.exists():
        return {}
    d = json.loads(HEALTH_JSON.read_text(encoding="utf-8"))
    return d.get("providers", {})


def load_free_models() -> list[dict]:
    d = json.loads(CONSOLIDATED.read_text(encoding="utf-8"))
    return [m for m in d.get("ranked", []) if m.get("is_free")]


def recommend_chain(
    free_models: list[dict],
    health: dict,
    top: int = DEFAULT_TOP,
) -> list[dict]:
    """Recomendação CxB: top free por CxB, 1 tier por provider, SEM filtro
    de health. Health só é anexado (uptime/p50) para o alerta.

    - Um tier por provider: o free de MAIOR CxB daquele provider.
    - Ordem: CxB desc (melhor score primeiro).
    - Sem filtro de inventário Hermes (o CxB já é a curadoria; o cache do
      Hermes é parcial — ex: nous=0 modelos — e filtraria demais).
    """
    best_by_prov: dict[str, dict] = {}
    for m in sorted(free_models, key=lambda m: -(m.get("cxb_score") or 0)):
        prov = m["provider"]
        if prov in EXCLUDED_PROVIDERS:
            continue
        if prov not in best_by_prov:
            best_by_prov[prov] = m
    chain: list[dict] = []
    for prov, m in sorted(best_by_prov.items(), key=lambda kv: -(kv[1].get("cxb_score") or 0)):
        h = health.get(prov) or {}
        chain.append({
            "provider": prov,
            "model": m["model_id"],
            "cxb_score": m.get("cxb_score") or 0.0,
            "uptime_pct": h.get("uptime_pct"),
            "p50_ms": h.get("p50_ms"),
            "last_ok": h.get("last_ok"),
        })
        if len(chain) >= top:
            break
    return chain


def parse_current_chain(text: str) -> list[tuple[str, str]]:
    """Extrai (provider, model) do bloco fallback_providers atual."""
    m = re.search(
        r"^fallback_providers:\n((?:\s+-\s+provider:.*\n\s+model:.*\n?)+)",
        text,
        re.MULTILINE,
    )
    if not m:
        return []
    block = m.group(1)
    out = []
    for pm, mm in re.findall(
        r"-\s+provider:\s*(\S+)\s*\n\s+model:\s*(\S+)", block
    ):
        out.append((pm.strip(), mm.strip()))
    return out


def _health_line(prov: str, health: dict) -> str:
    """Resumo de health de um provider p/ o alerta (com ⚠️ se ruim)."""
    h = health.get(prov) or {}
    up = h.get("uptime_pct")
    p50 = h.get("p50_ms")
    last_ok = h.get("last_ok")
    if up is None and p50 is None and last_ok is None:
        return "sem health"
    warn = (last_ok is False) or (up is not None and up < LOW_UPTIME_PCT)
    up_s = f"{up:.0f}%" if up is not None else "–"
    p50_s = (f"{p50/1000:.0f}s" if p50 >= 1000 else f"{p50:.0f}ms") if p50 is not None else "–"
    base = f"{up_s} · {p50_s}"
    return ("⚠️ " if warn else "") + base


def monitor(top: int = DEFAULT_TOP) -> dict:
    """Read-only: chain atual + health por tier + recomendação CxB."""
    health = load_health()
    free_models = load_free_models()
    cfg_text = CONFIG_YAML.read_text(encoding="utf-8")
    current = parse_current_chain(cfg_text)

    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "current": [
            {"provider": p, "model": m, "health": _health_line(p, health)}
            for p, m in current
        ],
        "recommended": recommend_chain(free_models, health, top=top),
        "problems": [],
    }
    # Tiers da chain atual com health ruim → problema informativo
    for t in result["current"]:
        h = health.get(t["provider"]) or {}
        if h.get("last_ok") is False or (
            h.get("uptime_pct") is not None and h["uptime_pct"] < LOW_UPTIME_PCT
        ):
            result["problems"].append(
                f"{t['provider']}/{t['model']}: health ruim ({t['health']})"
            )
    return result


def build_alert(res: dict) -> str:
    """Texto HTML (Telegram) do monitor."""
    lines = ["🔄 <b>fallback free</b> — monitor (benchmark-curatoria-diario)"]
    # Chain atual (manual)
    lines.append("\n<b>Chain atual (manual):</b>")
    for i, t in enumerate(res["current"], 1):
        lines.append(f"{i}. {t['provider']} → <code>{t['model']}</code> · {t['health']}")
    # Recomendação CxB
    rec = res["recommended"]
    if rec:
        lines.append("\n<b>Recomendação CxB (top free):</b>")
        for t in rec:
            lines.append(
                f"• {t['provider']}/{t['model']} (CxB {t['cxb_score']:.1f})"
            )
    # Problemas
    if res["problems"]:
        lines.append("\n⚠️ <b>Atenção:</b>")
        for p in res["problems"]:
            lines.append(f"• {p}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--alert", action="store_true", help="imprime o texto HTML p/ Telegram")
    args = ap.parse_args()
    if args.top < 1 or args.top > MAX_TIERS:
        print(f"--top fora do intervalo 1..{MAX_TIERS}", file=sys.stderr)
        return 2
    try:
        res = monitor(top=args.top)
    except Exception as e:  # noqa: BLE001
        print(f"monitor falhou: {e}", file=sys.stderr)
        return 2
    if args.alert:
        print(build_alert(res))
    else:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
