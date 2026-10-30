"""scripts/curate_daily.py
=======================

Curadoria diária do benchmark_geral — executada após probe health (07:30).

Fluxo:
1.  **Provider health check** — probe em todos os providers configurados
    (acumula em provider_health.jsonl). Identifica providers inativos.
2.  **Refresh caches** — models.dev, OpenRouter, AA (se expirados >24h).
3.  **Snapshot anterior** — conta modelos em consolidated_models.json
    (para detectar quedas >5% = possível deslistagem).
4.  **Pipeline completo** — extract → map_source → normalize → dedup →
    enrich (AA) → score → build → consolidated_models.json + index.html.
5.  **Validação mudanças**:
    - Provider desapareceu da listagem Hermes → alerta
    - Count caiu >5% vs ontem → alerta
    - Novo provider apareceu → alerta informativo
6.  **Auto-commit** se dashboard mudou.
7.  **Auto-push para GitHub** se confirmado.

Telegram: o stdout do cron É o canal de alerta (Hermes entrega stdout no
Telegram também com exit 0). Silencioso quando tudo verde. O monitor 2.5
(fallback chain) mantém send_telegram próprio.

Uso: `python scripts/curate_daily.py` (projeto cwd).
Exit codes: 0=ok (alertas informativos incluídos), 2=falha crítica.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from benchmark_pipe.extract import extract_provider_models  # noqa: E402

# probe_health agora vive em benchmark_providers (repo separado).
# Localizacao: pasta irma ../benchmark-providers. Override via PROVIDERS_HOME env var.
_PROVIDERS_HOME = Path(os.environ.get(
    "PROVIDERS_HOME",
    str(ROOT.parent / "benchmark-providers"),
))
# Reimportar de la: adicionar ao sys.path se nao estiver
if str(_PROVIDERS_HOME) not in sys.path:
    sys.path.insert(0, str(_PROVIDERS_HOME))

try:
    from benchmark_providers.probe_health import (  # noqa: E402
        aggregate,
        append_jsonl,
        detect_alert,
        read_jsonl,
        run as probe_run,
        send_telegram,
    )
    _PROBE_AVAILABLE = True
except ImportError as _e:
    logger_warn = f"benchmark_providers nao encontrado em {_PROVIDERS_HOME}: {_e}"
    _PROBE_AVAILABLE = False
    # Stubs que falham de forma explicita quando probe e' exigido
    def _missing(*a, **kw):
        raise RuntimeError(f"probe_health indisponivel: {logger_warn}")
    aggregate = append_jsonl = detect_alert = read_jsonl = probe_run = send_telegram = _missing

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("curate_daily")

# Diretórios-chave
DATA_DIR = ROOT / "data"
CONSOLIDATED = DATA_DIR / "consolidated_models.json"
PREV_SNAPSHOT = DATA_DIR / "consolidated_prev.json"
PROVIDER_HEALTH_JSONL = _PROVIDERS_HOME / "data" / "provider_health.jsonl"
PROVIDER_HEALTH_JSON = _PROVIDERS_HOME / "data" / "provider_health.json"

# Thresholds
DROP_THRESHOLD_PCT = 5.0  # alerta se modelos caírem >5% vs ontem
MIN_MODELS = 50  # sanity check

# Filtro para modelos obsoletos — removidos pelo provider
REMOVED_PROVIDERS = {"opencode-free"}  # opencode-free foi removido do Hermes


def _load_hermes_inventory() -> dict[str, set]:
    """Carrega provider_models_cache.json — fonte de verdade da LISTAGEM."""
    return extract_provider_models()


def _check_obsolete_models(curr: dict, hermes: dict[str, set]) -> list[str]:
    """Detecta modelos no consolidated que não estão mais no provider (Hermes)."""
    alerts = []
    
    # Índice de modelos ativos por provider
    active_json = json.loads(CONSOLIDATED.read_text(encoding="utf-8"))
    curr_models = {m.get("model_id") for m in active_json.get("ranked", [])}
    
    # 1. Se provider não está mais no Hermes → remover TODOS os modelos dele
    for prov in list(curr["by_provider"].keys()):
        if prov not in hermes and prov not in REMOVED_PROVIDERS:
            alerts.append(f"⚠️ Provider REMOVIDO do Hermes: {prov}")
    
    # 2. Modelos que estão no consolidated mas não na lista ativa do provider?
    # Simplificação: se model_id não está na lista do provider -> obsoleto
    # (não filtramos aqui — filtra no build. Só alertamos.)
    
    return alerts


def _run_cmd(cmd: list[str], check=True, timeout=300) -> tuple[int, str, str]:
    """Roda comando no ROOT, captura stdout/stderr.

    11/10/2026: errors="replace" — stderr de subprocesso pode vir em CP1252
    (ex.: stub da Microsoft Store), e um UnicodeDecodeError na reader thread
    do subprocess zera stdout/stderr (None), escondendo o erro real.
    """
    p = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if check and p.returncode != 0:
        logger.error("Comando falhou: %s\n%s", cmd, p.stderr[-300:])
    return p.returncode, p.stdout, p.stderr


def _snapshot_counts() -> dict:
    """Snapshot do consolidated atual para detectar deltas."""
    if not CONSOLIDATED.exists():
        return {}
    d = json.loads(CONSOLIDATED.read_text(encoding="utf-8"))
    ranked = d.get("ranked", [])
    non_ranked = d.get("non_ranked", [])
    by_provider = {}
    for m in ranked + non_ranked:
        p = m.get("provider", "?")
        by_provider[p] = by_provider.get(p, 0) + 1
    return {
        "ranked_count": len(ranked),
        "non_ranked_count": len(non_ranked),
        "total": len(ranked) + len(non_ranked),
        "by_provider": by_provider,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def _save_snapshot(snap: dict):
    PREV_SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_prev_snapshot() -> dict | None:
    if not PREV_SNAPSHOT.exists():
        return None
    try:
        return json.loads(PREV_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        return None


def _check_alerts(curr: dict, prev: dict | None, alerts: list[str]):
    """Detecta anomalias no inventário."""
    if prev:
        prev_total = prev.get("total", 0)
        curr_total = curr.get("total", 0)
        if prev_total > 0:
            drop_pct = 100 * (prev_total - curr_total) / prev_total
            if drop_pct > DROP_THRESHOLD_PCT:
                alerts.append(
                    f"⚠️ Count caiu {drop_pct:.1f}% ({prev_total} → {curr_total})"
                )

        # Provider desapareceu?
        prev_provs = set(prev.get("by_provider", {}).keys())
        curr_provs = set(curr.get("by_provider", {}).keys())
        missing = prev_provs - curr_provs
        new = curr_provs - prev_provs
        if missing:
            alerts.append(f"⚠️ Providers REMOVIDOS: {', '.join(sorted(missing))}")
        if new:
            alerts.append(f"ℹ️ Providers NOVOS: {', '.join(sorted(new))}")

    # Sanity check total
    if curr.get("total", 0) < MIN_MODELS:
        alerts.append(f"⚠️ Total muito baixo: {curr['total']} < {MIN_MODELS}")


def _format_health_summary(raw_alerts: list[str], probe_cfg: dict, agg: dict) -> list[str]:
    """Resumo de saúde em 1 linha por categoria (stdout do cron = canal único).

    raw_alerts vem de probe_run(alert=False), que NÃO aplica o filtro
    `alerts:false` (o filtro em probe_health.run() só roda com alert=True) —
    filtrar aqui. Categorias:
      🏥 falha real | 🟡 instável (não alertou, uptime <100%) |
      🟢 OK | 🚫 sem credencial (alerts:false — falha por design)
    """
    by_design = {
        n for n, pc in probe_cfg.get("providers", {}).items()
        if pc.get("alerts") is False
    }
    fail_real = sorted(p for p in raw_alerts if p not in by_design)
    fail_design = sorted(p for p in raw_alerts if p in by_design)
    stable: list[str] = []
    unstable: list[str] = []
    for p in sorted(agg):
        if p in raw_alerts:
            continue
        up = agg[p].get("uptime_pct")
        if up is None or float(up) == 100.0:
            stable.append(p)
        else:
            unstable.append(f"{p} ({up}%)")
    out: list[str] = []
    if fail_real:
        out.append(f"🏥 Falha ({len(fail_real)}): {', '.join(fail_real)}")
    if unstable:
        out.append(f"🟡 Instável ({len(unstable)}): {', '.join(unstable)}")
    if stable:
        out.append(f"🟢 OK ({len(stable)}): {', '.join(stable)}")
    if fail_design:
        out.append(f"🚫 Sem credencial, by design ({len(fail_design)}): {', '.join(fail_design)}")
    return out


def main() -> int:
    alerts: list[str] = []
    logger.info("=== benchmark-curatoria-diario ===")

    # 1. PROVIDER HEALTH — probe antes de qualquer coisa
    logger.info("Passo 1: provider health probe...")
    probe_cfg = json.loads((_PROVIDERS_HOME / "scripts" / "probe_config.json").read_text(encoding="utf-8"))
    probe_res = probe_run(
        config_path=_PROVIDERS_HOME / "scripts" / "probe_config.json",
        jsonl_path=PROVIDER_HEALTH_JSONL,
        aggregate_path=PROVIDER_HEALTH_JSON,
        alert=False,  # sem Telegram aqui: stdout do cron é o canal único
    )
    if probe_res["alerts"]:
        # alert=False NÃO aplica o filtro alerts:false do probe_health.run
        # (o filtro só roda com alert=True) — _format_health_summary filtra
        # e compacta (1 linha por categoria, inclui 🟢 OK).
        alerts.extend(_format_health_summary(
            probe_res["alerts"], probe_cfg, probe_res["aggregate"],
        ))

    # 1.5 LIVENESS — ping diário nos modelos NIM free (nim_pipeline/liveness.py).
    #     Identifica vivos/mortos (410/404) ANTES do trabalho pesado e grava
    #     data/liveness_daily.json (cache diário; consultável com --status).
    #     Best-effort: falha vira alerta, não derruba a curadoria. Dia normal é
    #     silencioso (stdout limpo) — alerta só em anomalia (0 vivos/novos mortos).
    logger.info("Passo 1.5: liveness ping modelos NIM free...")
    try:
        from nim_pipeline.liveness import run_liveness, anomalies
        alerts.extend(anomalies(run_liveness()))
    except Exception as e:  # noqa: BLE001
        alerts.append(f"🩺 liveness falhou (não bloqueia): {e}")

    # 2. REFRESH CACHES — models.dev / OpenRouter / AA
    logger.info("Passo 2: refresh caches (--refresh)...")
    # Forçamos refresh das APIs (modelos.dev, OpenRouter, AA) de forma leve.
    # run_consolidated.py --refresh faz isso, mas com build. Queremos só
    # refresh aqui, build vem depois.
    code_refresh, _, err_refresh = _run_cmd(
        [sys.executable, "scripts/run_consolidated.py", "--refresh", "--json", str(CONSOLIDATED)],
        check=False,
        timeout=300,
    )
    if code_refresh != 0:
        # fallback: tentar com use-cache se refresh falhar (offline mode)
        logger.warning("Refresh falhou (%s), tentando --use-cache", err_refresh[-200:])
        code_cache, _, err_cache = _run_cmd(
            [sys.executable, "scripts/run_consolidated.py", "--use-cache", "--json", str(CONSOLIDATED)],
            check=False,
            timeout=300,
        )
        if code_cache != 0:
            alerts.append("⚠️ Pipeline falhou mesmo com --use-cache")
            print("\n".join(alerts))  # stdout → trail em cron/output/
            send_telegram("\n".join(alerts))  # redundância p/ falha crítica
            return 2

    # 2.5 MONITOR — fallback free (READ-ONLY: rotação é 100% manual)
    #     Lê a chain atual do config.yaml, cruza com health real e calcula a
    #     recomendação CxB. Dispara alerta diário no Telegram (não escreve
    #     no config). Nunca quebra a curadoria — falha vira alerta, não exit != 0.
    logger.info("Passo 2.5: monitor fallback free...")
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib.util as _iutil
        _spec = _iutil.spec_from_file_location(
            "rotate_best_free", ROOT / "scripts" / "rotate_best_free.py"
        )
        rot = _iutil.module_from_spec(_spec)
        _spec.loader.exec_module(rot)
        res = rot.monitor(top=rot.DEFAULT_TOP)
        # Alerta diário no Telegram (chain atual + health + recomendação CxB).
        # Health ruim já está no relatório (⚠️) — NÃO vai em `alerts`, porque a
        # rotação é manual: health ruim é informativo, não falha do pipeline.
        send_telegram(rot.build_alert(res))
    except Exception as e:  # noqa: BLE001 — monitor é best-effort
        alerts.append(f"🔄 monitor fallback falhou (não bloqueia): {e}")

    # 3. SNAPSHOT — comparar com anterior
    logger.info("Passo 3: validando mudanças no inventário...")
    curr = _snapshot_counts()
    prev = _load_prev_snapshot()
    _check_alerts(curr, prev, alerts)
    _save_snapshot(curr)

    # 4. AUTO-COMMIT — commit se consolidated mudou
    logger.info("Passo 4: auto-commit...")
    git_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    dirty = [l for l in git_status.stdout.splitlines() if l.strip()]
    if dirty:
        # Commit consolidado + index.html
        add_msg = f"dashboard curadoria {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
        _run_cmd(["git", "add", "data/consolidated_models.json", "index.html"], check=False)
        commit_res = _run_cmd(
            ["git", "commit", "-m", add_msg],
            check=False,
        )
        if commit_res[0] == 0:
            logger.info("Commit criado: %s", add_msg)
            # 5. AUTO-PUSH
            logger.info("Passo 5: push automático...")
            push_res = _run_cmd(["git", "push", "origin", "main"], check=False)
            if push_res[0] != 0:
                alerts.append(f"⚠️ Push falhou: {push_res[2][-200:]}")
            else:
                logger.info("Push OK: origin main")
        else:
            msg = (commit_res[1] + commit_res[2]).lower()
            if "nothing to commit" not in msg:
                alerts.append(f"⚠️ Commit falhou: {commit_res[2][-200:]}")
            else:
                logger.info("Nada novo para commitar.")
    else:
        logger.info("Working tree limpo — nada a commitar.")

    # Report
    logger.info("=== Resultado: %d alertas ===", len(alerts))
    for a in alerts:
        logger.warning(a)

    if alerts:
        # 13/10/2026: stdout do cron É o canal de alerta — Hermes entrega o
        # stdout no Telegram também com exit 0 (delivery_outcome=delivered,
        # validado 12-13/10). O send_telegram daqui + o interno do probe da
        # light + a entrega do cron somavam 3 mensagens/dia com o mesmo
        # conteúdo. Monitor 2.5 (chain fallback) mantém send_telegram próprio.
        print("\n".join(alerts))
        return 0

    return 0  # silencioso


if __name__ == "__main__":
    raise SystemExit(main())
