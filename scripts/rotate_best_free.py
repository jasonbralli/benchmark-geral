"""scripts/rotate_best_free.py
=============================

Rotação automática do fallback chain do Hermes para o melhor modelo free
disponível, cruzando:

  1. **Curadoria CxB** — `data/consolidated_models.json` (score.py:
     benefit/custo, modelos free dominam com cost=0).
  2. **Health real** — `../benchmark_providers/data/provider_health.json`
     (probe diário: uptime 24h, shed, last_ok, latência).
  3. **Inventário vivo** — `provider_models_cache.json` do Hermes
     (sanitização: modelo só entra se estiver listado no provider).

Regras de seleção (estáveis, anti-flapping):
- Só provider com `last_ok == true` E `samples >= MIN_SAMPLES` (24h).
- Só modelo `is_free` E presente no inventário do provider (sem fantasma).
- Dedup por `canonical_id` (o mesmo modelo lógico não ocupa 2 tiers).
- Tiers com providers DISTINTOS (rotação real de provider).
- Mesma canonical em vários providers saudáveis → ganha o provider mais
  saudável/rápido (uptime desc, p50 asc).
- **Idempotente**: se a chain calculada == chain atual do config.yaml →
  no-op silencioso (sem churn de config).

Escrita do config.yaml:
- Backup `config.yaml.bak.<epoch>` antes de qualquer escrita.
- Substituição cirúrgica SÓ do bloco `fallback_providers:` (regex
  multiline) — o resto do arquivo é byte-idêntico (sem round-trip YAML).
- Validação pós-escrita: re-lê o arquivo e confere os (provider, model).

Uso:
    python scripts/rotate_best_free.py              # aplica
    python scripts/rotate_best_free.py --dry-run    # só mostra
    python scripts/rotate_best_free.py --top 3      # tiers (default 3)

Exit codes: 0=ok (incl. no-op), 1=alerta (roteou ou falha parcial), 2=falha crítica.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
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

MIN_SAMPLES = 3      # mínimo de samples 24h p/ provider ser elegível
DEFAULT_TOP = 3      # tiers no fallback chain
MAX_TIERS = 5

# Providers que NUNCA entram no fallback chain (não são "free provider" de verdade
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


def load_inventory() -> dict[str, set]:
    """provider_models_cache.json do Hermes — fonte da verdade da listagem."""
    from benchmark_pipe.extract import extract_provider_models
    return extract_provider_models()


def _provider_rank(prov: str, health: dict) -> tuple:
    """Menor = melhor. Uptime desc, p50 asc, shed asc."""
    h = health.get(prov) or {}
    uptime = h.get("uptime_pct")
    p50 = h.get("p50_ms")
    shed = h.get("shed_hits")
    return (
        -(uptime if uptime is not None else -1.0),
        p50 if p50 is not None else float("inf"),
        shed if shed is not None else 0,
    )


def build_chain(
    free_models: list[dict],
    health: dict,
    inventory: dict[str, set],
    top: int = DEFAULT_TOP,
) -> list[dict]:
    """Greedy: melhor canonical × melhor provider saudável, providers distintos."""
    # 1) dedup por canonical: melhor cxb por canonical
    best_by_canon: dict[str, dict] = {}
    for m in sorted(free_models, key=lambda m: -(m.get("cxb_score") or 0)):
        cid = m.get("canonical_id") or m["model_id"]
        if cid not in best_by_canon:
            best_by_canon[cid] = m
    # 2) candidatos: (canonical, provider) onde provider é saudável e lista o modelo
    candidates: list[tuple[float, tuple, str, str, dict]] = []
    for cid, m in best_by_canon.items():
        for prov in {m["provider"]}:
            h = health.get(prov) or {}
            if not h.get("last_ok"):
                continue
            if (h.get("samples") or 0) < MIN_SAMPLES:
                continue
            if prov in EXCLUDED_PROVIDERS:
                continue
            if prov not in inventory:
                continue
            # sanitização: o model_id exato (ou o canonical) precisa estar listado
            listed = inventory[prov]
            if m["model_id"] not in listed and cid not in listed:
                continue
            candidates.append((
                m.get("cxb_score") or 0.0,
                _provider_rank(prov, health),
                cid,
                m["model_id"],
                m,
            ))
    # 3) greedy: cxb desc p/ escolher o melhor modelo de cada provider;
    #    a ORDEM final da chain é por usabilidade do provider (p50 asc,
    #    uptime desc) — provider rápido e saudável primeiro; provider lento
    #    (ex: nvidia ~114s TTFT) vira último recurso, não primeiro tier.
    candidates.sort(key=lambda c: (-c[0], c[1]))
    chain: list[dict] = []
    used_provs: set[str] = set()
    for cxb, prank, cid, model_id, m in candidates:
        prov = m["provider"]
        if prov in used_provs:
            continue
        used_provs.add(prov)
        chain.append({
            "provider": prov,
            "model": model_id,
            "canonical_id": cid,
            "cxb_score": cxb,
            "uptime_pct": (health.get(prov) or {}).get("uptime_pct"),
            "p50_ms": (health.get(prov) or {}).get("p50_ms"),
            "_prank": prank,
        })
        if len(chain) >= top:
            break
    chain.sort(key=lambda t: t.pop("_prank"))
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


def render_chain(chain: list[dict]) -> str:
    lines = ["fallback_providers:"]
    for t in chain:
        lines.append(f"  - provider: {t['provider']}")
        lines.append(f"    model: {t['model']}")
    return "\n".join(lines) + "\n"


def replace_fallback_block(text: str, chain: list[dict]) -> str | None:
    """Substitui cirurgicamente o bloco fallback_providers. None = sem bloco atual."""
    new_block = render_chain(chain)
    m = re.search(
        r"^fallback_providers:\n(?:\s+-\s+provider:.*\n\s+model:.*\n?)+",
        text,
        re.MULTILINE,
    )
    if m:
        return text[: m.start()] + new_block + text[m.end():]
    # Sem bloco: insere antes da primeira chave top-level seguinte conhecida
    m2 = re.search(r"^(?! )\S", text, re.MULTILINE)
    if not m2:
        return None
    return text[: m2.start()] + new_block + "\n" + text[m2.start():]


def validate_chain(chain: list[dict], inventory: dict[str, set]) -> list[str]:
    """Pós-escrita: confere que cada (provider, model) está no inventário vivo."""
    problems = []
    for t in chain:
        prov, model = t["provider"], t["model"]
        listed = inventory.get(prov, set())
        if model not in listed and t.get("canonical_id") not in listed:
            problems.append(f"{prov}/{model} ausente do inventário Hermes")
    return problems


def rotate(
    top: int = DEFAULT_TOP,
    dry_run: bool = False,
    notify: bool = True,
) -> dict:
    health = load_health()
    free_models = load_free_models()
    inventory = load_inventory()

    chain = build_chain(free_models, health, inventory, top=top)
    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "chain": chain,
        "changed": False,
        "dry_run": dry_run,
        "problems": [],
    }
    if not chain:
        result["problems"].append("nenhum provider free saudável — config NÃO tocada")
        return result

    cfg_text = CONFIG_YAML.read_text(encoding="utf-8")
    current = parse_current_chain(cfg_text)
    target = [(t["provider"], t["model"]) for t in chain]
    result["current"] = current
    result["target"] = target

    if current == target:
        result["changed"] = False  # idempotente: nada a fazer
        return result

    if dry_run:
        result["changed"] = True
        return result

    # Backup + escrita cirúrgica
    bak = CONFIG_YAML.with_name(f"config.yaml.bak.{int(time.time())}")
    bak.write_text(cfg_text, encoding="utf-8")
    new_text = replace_fallback_block(cfg_text, chain)
    if new_text is None:
        result["problems"].append("não foi possível localizar bloco fallback — abortado")
        return result
    CONFIG_YAML.write_text(new_text, encoding="utf-8")

    # Validação pós-escrita (re-lê do disco)
    written = parse_current_chain(CONFIG_YAML.read_text(encoding="utf-8"))
    if written != target:
        result["problems"].append(
            f"config diverge após escrita: {written} != {target}"
        )
    result["problems"].extend(validate_chain(chain, inventory))
    result["backup"] = str(bak)
    result["changed"] = True
    return result


def _notify(result: dict) -> None:
    """Telegram via send_telegram do probe (best-effort, nunca quebra)."""
    try:
        sys.path.insert(0, str(ROOT.parent / "benchmark_providers"))
        from benchmark_providers.probe_health import send_telegram
    except Exception:
        return
    if not result["changed"]:
        return  # silencioso quando verde
    lines = ["🔄 Rotação fallback free (benchmark_geral)"]
    for i, t in enumerate(result["chain"], 1):
        lines.append(
            f"{i}. {t['provider']} → {t['model']} "
            f"(CxB {t['cxb_score']:.1f}, uptime {t['uptime_pct']}%)"
        )
    if result["problems"]:
        lines.append("⚠️ " + "; ".join(result["problems"]))
    send_telegram("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    args = ap.parse_args()
    if args.top < 1 or args.top > MAX_TIERS:
        print(f"--top fora do intervalo 1..{MAX_TIERS}", file=sys.stderr)
        return 2

    result = rotate(top=args.top, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["problems"] and not result["changed"]:
        return 2
    if result["problems"]:
        _notify(result)
        return 1
    if result["changed"]:
        _notify(result)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
