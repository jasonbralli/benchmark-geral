# Plano de Implementação — Enriquecimento Dashboard v2.5

**Data**: 16/09/2026  
**Baseline**: `cf12a6d` (110 testes verdes, dashboard live em  
https://jasonbralli.github.io/benchmark-geral/)  
**Objetivo**: expor campos já coletados (AA + models.dev + OpenRouter) como  
colunas/filtros novos, sem quebrar o pipeline atual.

---

## Estratégia geral

1. **Sem novas dependências** — tudo vem dos caches existentes.
2. **Backward compatible** — campos novos adicionados, nenhum removido.
3. **Testes primeiro** — cada bloco abre com teste novo, depois implementa.
4. **Commits atômicos** por bloco (1 commit/intenção).

---

## Fase 1 — Schema & payload (`benchmark_pipe/`)

### 1.1 Extender `UnifiedModel`

Arquivo: `benchmark_pipe/normalize.py`

Adicionar campos (todos `Optional`, default `None`):

```python
# Performance (AA)
speed_tps: float | None = None           # median_output_tokens_per_second
ttft_s: float | None = None              # median_time_to_first_token_seconds
e2e_s: float | None = None               # median_end_to_end_response_time_seconds

# Quality sub-scores (AA)
coding_index: float | None = None        # artificial_analysis_coding_index
agentic_index: float | None = None       # artificial_analysis_agentic_index

# Capability metadata (models.dev / OpenRouter)
modalities_in: list[str] | None = None   # ["text","image","audio"]
modalities_out: list[str] | None = None  # ["text","image"]
max_output_tokens: int | None = None     # limit.output / max_completion_tokens
open_weights: bool | None = None
knowledge_cutoff: str | None = None      # "2024-12" (models.dev)
attachment: bool | None = None           # aceita file upload
```

**Por quê Optional**: preserva compat com providers sem metadata (passthrough).  
**Teste novo**: `tests/test_normalize.py::test_unified_model_extended_fields`

### 1.2 Capturar campos em `normalize_nvidia()` e `normalize_openrouter()`

Arquivo: `benchmark_pipe/normalize.py`

- **NVIDIA/models.dev**: extrair `modalities.input/output`, `limit.output`,
  `open_weights`, `knowledge`, `attachment` do dict já vindo do cache.
- **OpenRouter**: extrair de `architecture.input_modalities/output_modalities`,
  `top_provider.max_completion_tokens`, `hugging_face_id` (sinaliza open weights).

**Teste novo**: validar extração com fixtures reais (sample do cache).

### 1.3 Capturar novos campos AA em `aa_api.py`

Arquivo: `benchmark_pipe/aa_api.py`

Mudar `build_aa_index_map()` para retornar dict mais rico:

```python
# Antes: {slug_norm: intelligence_index}
# Depois: {slug_norm: {"aa_index": ..., "speed_tps": ..., "ttft_s": ...,
#                      "coding_index": ..., "agentic_index": ..., "e2e_s": ...}}
```

Ou manter `build_aa_index_map()` legacy e adicionar `build_aa_metrics_map()`.

**Teste novo**: `test_aa_api.py::test_aa_metrics_map_full_fields`

### 1.4 Propagar via `enrich.py`

Arquivo: `benchmark_pipe/enrich.py`

Patch `enrich_unified()` para, quando encontrar slug no mapa AA, popular os 5
campos novos (além de `aa_index`). Idempotente — só preenche se `None`.

**Teste novo**: `test_enrich.py::test_enrich_speed_ttft_propagation`  
**Teste novo**: `test_enrich.py::test_enrich_free_variant_inherits_speed`  
(padrão do `test_enrich_free_variant_inherits_aa`)

### 1.5 Expôr no payload (`build.py`)

Arquivo: `benchmark_pipe/build.py`

Adicionar as chaves novas ao dicionário do modelo no payload. **Manter ordem
alfabética/lógica**, não alterar chaves existentes (JS atual depende).

**Teste novo**: `test_build_consolidado.py::test_payload_has_speed_fields`

---

## Fase 2 — Template & filtros (`template_consolidado.html`)

### 2.1 Colunas novas na tabela ranked

Adicionar colunas (todas ordenáveis via click no header):

| Coluna | Fonte | Formatação | Tooltip |
|---|---|---|---|
| `tok/s` | `speed_tps` | `34.0` | "Median output tokens/sec (AA)" |
| `TTFT` | `ttft_s` | `1.2s` | "Time to first token (median)" |
| `Coding` | `coding_index` | `76.9` | "AA Coding Index" |
| `Agentic` | `agentic_index` | `51.6` | "AA Agentic Index" |
| `Modal` | `modalities_out` | `T I A` chips | "Output modalities" |
| `Max Out` | `max_output_tokens` | `16384` | "Max output tokens" |
| `Open` | `open_weights` | 🔓 ou — | "Open weights" |

**JS**: implementar `sortBy(key)` genérico tratando `null`/`undefined` (vai pro
fim). Reusar padrão do `renderRanked()` existente.

**Teste node --check** após patch (regra do projeto).

### 2.2 Filtros novos (todos client-side)

Adicionar em `state`:

```js
state = {
  ...atuais,
  minSpeed: 0,        // tok/s
  maxTtft: null,      // seconds
  hasCoding: false,   // só com coding_index
  hasAgentic: false,
  modality: null,     // null|'image'|'audio'|'video' — exige em modalities_in
  openOnly: false,
  useCase: null,      // preset: 'chat'|'code'|'vision'|'longctx'|'fast'|'cheap'|'agentic'
};
```

### 2.3 Presets de use-case (dropdown)

Mapeamento (aplicado como conjunto de filtros):

| Preset | Filtros aplicados |
|---|---|
| `chat` | ctx≥32k, tools=true, sort=cxb |
| `code` | hasCoding=true, sort=coding desc |
| `vision` | modality='image' |
| `longctx` | ctx≥256k, sort=ctx desc |
| `fast` | minSpeed=80, sort=speed desc |
| `cheap` | free only, sort=cxb |
| `agentic` | hasAgentic=true, tools=true, sort=agentic desc |

Reset table search/texto ao trocar preset.

### 2.4 KPIs novos

Adicionar 4 cards no topo:

- **Median Speed**: mediana do `speed_tps` dos modelos rankeados
- **Fastest**: max `speed_tps` (exibe modelo)
- **Best Coding**: max `coding_index`
- **Best Agentic**: max `agentic_index`

---

## Fase 3 — Testes

Arquivo novo: `tests/test_enrichment_extended.py`

```python
test_unified_model_schema_extended      # campos novos existem
test_normalize_nvidia_modalities         # extração de modalities
test_normalize_openrouter_arch           # architecture modalities
test_aa_metrics_map_includes_speed       # aa_api retorna speed_tps
test_enrich_propagates_speed             # enrich povoa speed_tps
test_enrich_free_inherits_speed          # variante :free herda
test_payload_carries_new_fields          # build expõe no JSON
test_backward_compat                     # campos antigos intactos
```

**Target**: 110 + 8 = **118 testes verdes**.

---

## Fase 4 — Idempotência, validação, deploy

1. Rodar `python scripts/run_consolidated.py --use-cache` 2x → byte-idêntico.
2. Chrome headless `--dump-dom` no dashboard: conferir novas colunas + footer.
3. `python -m pytest -q` → 118 verdes.
4. Commit atômico por fase, push final via `scripts/push_github.py`.

---

## Rollback plan

Se algo quebrar:
- Branch main → `git revert HEAD~N` até o commit do cleanup (`8b8210b`).
- gh-pages → re-rodar `scripts/push_github.py` da versão boa.

---

## Riscos & mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| AA cache não tem métricas p/ alguns modelos | Alta (~40%) | Colunas mostram `—` quando null |
| JS do template quebrar | Média | `node --check` após cada patch |
| Idempotência quebrar | Baixa | diff byte-a-byte em `test_build_consolidado.py` |
| Performance client-side piora (1156 linhas) | Baixa | Manter render única, sem observers |

---

## Estimativa

- **Fase 1**: ~90 min (schema + extract + enrich + build + testes)
- **Fase 2**: ~90 min (template + filtros + JS sorting)
- **Fase 3**: ~30 min (consolidar testes)
- **Fase 4**: ~15 min (validação + commit + push)

**Total**: ~3.5h de trabalho efetivo.
