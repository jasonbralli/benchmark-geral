# Changelog — benchmark_geral

## [v2.2.0] — 2026-08-21 — Sync Hermes + Auto-update

### ✨ Novos Scripts

- **`sync_hermes_models.py`** — Monitora `provider_models_cache.json` do Hermes,
  detecta modelos NVIDIA NIM novos, classifica em (frontier, specialized, variants),
  salva snapshot + TXT.

- **`update_pipeline.py`** — Pipeline auto-completo: merge (models.dev + txt sync),
  filtro Opção A, enrich AA Index, atualiza MD scorecard, regenera dashboard, pytest.

- **`run_full_pipeline.py`** — Orquestrador master: sync + update em 1 comando.

### 🎯 Mudanças Funcionais

- **Cache pipeline**: `nvidia_models_raw.json` agora 101 modelos (era 100).
  Adicionado `moonshotai/kimi-k3` (released 2026-07-16, 2.8T params, 1M context).

- **Scorecard top 10**: novo #1 = `moonshotai/kimi-k3` (AA=57, ★★★★★, Tier S).

- **AA Index calibration**: nova entrada em `nim_pipeline/enrich.py`:
  ```python
  "moonshotai/kimi-k3": {"index": 57, "url": "https://artificialanalysis.ai/models/kimi-k3"}
  ```

- **MD scorecard**: tabela atualizada com kimi-k3 no topo, poolside/laguna-xs-2.1
  como N/D no final.

### 🔄 Cron Job

- Atualizado `benchmark-geral-nim-quinzenal` para usar `run_full_pipeline.py --refresh`
  (antes usava só `run_pipeline.py --refresh`).

### 📚 Skill

- `benchmark-geral-automation` atualizada com:
  - Novos comandos (sync_hermes_models, update_pipeline, run_full_pipeline)
  - Seção "Pipeline Automatizado v2.1"
  - 4 novos pitfalls (Hermes cache filter, scorecard manual vs auto, aa_rank cross-tier, datetime import)

### 🧪 Testes

- 39 testes pytest passando (sem mudanças).
- Novo script `update_pipeline.py` validado end-to-end.

### 📊 Diff resumido

| Métrica | v2.1 | v2.2 |
|---------|------|------|
| Modelos no inventário | 100 | 101 |
| Frontier (Opção A) | 23 | 24 |
| Com AA Index | 7 | 8 |
| Scorecard size | 10 | 10 |
| Scripts Python | 2 | 5 |
| Cron job | manual | auto-sync |

---

## [v2.1.0] — 2026-08-16 — Pipeline Inicial

### Adicionado

- Pipeline Python de ranking NVIDIA NIM.
- Inventário via `models.dev/api.json`.
- Filtro Opção A: tool_call=True AND (reasoning OR release≥2026) AND ctx≥128K.
- AA Intelligence Index v4.1 curado em `enrich.AA_INTELLIGENCE_INDEX`.
- Dashboard estático `dashboard.html` com 4 blocos.
- Cron job quinzenal `benchmark-geral-nim-quinzenal`.
