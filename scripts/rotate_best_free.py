"""scripts/rotate_best_free.py
=============================

MONITOR do fallback chain free do Hermes (read-only — NÃO escreve no config).

A rotação é 100% manual (o usuário aplica a chain no config.yaml via UI).
Este script só **monitora e alerta**:

  1. Lê a **chain atual** do `config.yaml` (`fallback_providers:`).
  2. Cruza cada tier com o **health real** (uptime/p50/last_ok) e marca
     tiers com health ruim (⚠️).
  3. Calcula a **recomendação CxB** aplicando 4 filtros objetivos (ao vivo):
     só free + vivos (liveness status ok) + CxB > 50 + com AA (aa_index),
     ordenada pelo melhor Score CxB, top 5.
  4. Gera um alerta HTML para o Telegram (enviado pelo curate_daily).

Fontes:
  1. Curadoria CxB — data/consolidated_models.json (is_free, cxb_score, aa_index).
  2. Health real — ../benchmark-providers/data/provider_health.json
     (probe diário: uptime 24h, p50, last_ok).
  3. Liveness diário — data/liveness_daily.json (prova real de modelo vivo).
  4. Config do Hermes — fallback_providers: (chain manual atual).

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

# provider_health.json — override via PROVIDERS_DATA_DIR
PROVIDERS_DATA_DIR = Path(
    os.environ.get("PROVIDERS_DATA_DIR", str(ROOT.parent / "benchmark-providers" / "data"))
)
HEALTH_JSON = PROVIDERS_DATA_DIR / "provider_health.json"
CONSOLIDATED = ROOT / "data" / "consolidated_models.json"
CONFIG_YAML = Path(os.environ.get(
    "HERMES_CONFIG_YAML",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "config.yaml"),
))

DEFAULT_TOP = 5      # posições exibidas na recomendação CxB (3 a 5, pedido do user)
MAX_TIERS = 10
# Uptime abaixo disso (em %) marca o tier com ⚠️ no alerta
LOW_UPTIME_PCT = 50.0
# Limite de custo x benefício para entrar na recomendação
MIN_CXB = 50.0

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


def load_liveness() -> dict:
    """model_id -> resultado do liveness diário (best-effort, nunca quebra)."""
    p = ROOT / "data" / "liveness_daily.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {r.get("model_id"): r for r in (d.get("results", []) or []) if r.get("model_id")}


def recommend_chain(
    free_models: list,
    health: dict,
    liveness: dict | None = None,
    top: int = DEFAULT_TOP,
) -> list:
    """Recomendação CxB — 4 filtros objetivos (mesmo critério usado ao vivo):

    1. só free            -> is_free True  (já filtrado em load_free_models)
    2. vivos              -> liveness status == "ok" (prova real de hoje)
    3. CxB > 50           -> cxb_score acima de 50
    4. com AA             -> aa_index preenchido (não None)

    Ordenação: CxB desc (melhor score primeiro). Retorna até `top` posições.
    Health e liveness são anexados a cada item apenas para o alerta.
    """
    lv = liveness or {}
    chain = []
    for m in sorted(free_models, key=lambda m: -(m.get("cxb_score") or 0)):
        prov = m["provider"]
        if prov in EXCLUDED_PROVIDERS:
            continue
        cxb = m.get("cxb_score") or 0.0
        if cxb <= MIN_CXB:
            continue
        aa = m.get("aa_index")
        if aa is None:
            continue  # sem medição de Ambiente Apropriado → fica de fora
        mid = m["model_id"]
        lv_r = lv.get(mid) or {}
        if lv_r.get("status") != "ok":
            continue  # não está comprovadamente vivo hoje
        h = health.get(prov) or {}
        chain.append({
            "provider": prov,
            "model": mid,
            "cxb_score": cxb,
            "aa_index": aa,
            "uptime_pct": h.get("uptime_pct"),
            "p50_ms": h.get("p50_ms"),
            "last_ok": h.get("last_ok"),
            "liveness": lv_r.get("status"),
            "ttft_ms": lv_r.get("ttft_ms"),
        })
        if len(chain) >= top:
            break
    return chain


def parse_current_chain(text: str) -> list:
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


def _liveness_label(model_id: str, liveness: dict) -> str:
    """Marca de liveness do modelo p/ a chain atual (exibida no alerta)."""
    r = liveness.get(model_id) or {}
    status = r.get("status")
    alive = r.get("alive")
    if status == "ok" and alive:
        return "🩺 vivo"
    if r:
        return "🔴 morto"
    return ""


def monitor(top: int = DEFAULT_TOP) -> dict:
    """Read-only: chain atual + health/liveness por tier + recomendação CxB (4 filtros)."""
    health = load_health()
    free_models = load_free_models()
    liveness = load_liveness()
    cfg_text = CONFIG_YAML.read_text(encoding="utf-8")
    current = parse_current_chain(cfg_text)

    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "current": [
            {
                "provider": p,
                "model": m,
                "health": _health_line(p, health),
                "liveness": _liveness_label(m, liveness),
            }
            for p, m in current
        ],
        "recommended": recommend_chain(free_models, health, liveness, top=top),
        "problems": [],
    }
    # Tiers da chain atual com health ruim ou liveness morto → problema informativo
    for t in result["current"]:
        h = health.get(t["provider"]) or {}
        health_ruim = h.get("last_ok") is False or (
            h.get("uptime_pct") is not None and h["uptime_pct"] < LOW_UPTIME_PCT
        )
        lv_morto = t.get("liveness") == "🔴 morto"
        if health_ruim or lv_morto:
            result["problems"].append(
                f"{t['provider']}/{t['model']}: health ruim ({t['health']})"
                + (f" · liveness morto" if lv_morto else "")
            )
    return result


def build_alert(res: dict) -> str:
    """Texto HTML (Telegram) do monitor."""
    lines = ["🔄 <b>fallback free</b> — monitor (benchmark-curatoria-diario)"]
    # Chain atual (manual)
    lines.append("\n<b>Chain atual (manual):</b>")
    for i, t in enumerate(res["current"], 1):
        lv_s = f" · {t['liveness']}" if t.get("liveness") else ""
        lines.append(f"{i}. {t['provider']} → <code>{t['model']}</code> · {t['health']}{lv_s}")
    # Problemas primeiro (verificação antes da recomendação)
    if res["problems"]:
        lines.append("\n⚠️ <b>Atenção:</b>")
        for p in res["problems"]:
            lines.append(f"• {p}")
    # Recomendação CxB — já pré-filtrada pelos 4 filtros em recommend_chain().
    rec = res["recommended"]
    if rec:
        lines.append("\n<b>Recomendação CxB (top free):</b>")
        for t in rec:
            aa = t.get("aa_index")
            aa_s = f"{aa:.1f}" if isinstance(aa, (int, float)) else "–"
            lines.append(
                f"• {t['provider']}/{t['model']} (CxB {t['cxb_score']:.1f}, AA {aa_s})"
            )
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
