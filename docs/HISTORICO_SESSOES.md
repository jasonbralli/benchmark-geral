# Histórico de Sessões — benchmark_geral

Registro cronológico das sessões de desenvolvimento do pipeline consolidado
multi-provider, com os artefatos e decisões mais relevantes. Atualizado em
**23/08/2026**.

> Fonte: buscas em sessões passadas do Hermes (`session_search`).

---

## Linha do tempo

### 14/08/2026 — `@session:default/20260814_190805_e6c4f7` — Criação do pipeline NVIDIA NIM

- Pipeline Python de **ranking NVIDIA NIM**: `nim_pipeline/{fetch,filter,enrich}.py` → `build_dashboard.py` → `dashboard.html`.
- Fonte de inventário: `models.dev/api.json` (mirror da **API oficial NIM** `integrate.api.nvidia.com/v1`).
- **Critério Opção A**: `tool_call=True` AND (`reasoning` OR `release≥2026`) AND `ctx≥128K` → 23 modelos Tier S/A.
- AA Intelligence Index v4.1 curado em `enrich.AA_INTELLIGENCE_INDEX` (calibração 5★≥50|4★≥35|3★≥20|2★≥10).
- Repo privado criado: `jasonbralli/benchmark-geral-nim`. 39 testes pytest.
- Cron `benchmark-geral-nim-quinzenal` (`0 7 */15 * *`).

### 15/08/2026 — `@session:default/20260815_121105_e1ee75` — Padronização de colunas

- Todos os blocos (Scorecard Top 10, Tier S, Tier A) agora exibem as **mesmas colunas**:
  Rank, Modelo, Context, Release, AA Index, AA ★, Notas.
- Removidas colunas redundantes (Tier, Reasoning, tool-call e AA X/100 em notas).
- README atualizado com o schema padronizado.

### 21/08/2026 — `@session:default/20260821_145232_c81643` — Organização da estrutura + Pipeline v2.2

- **Reorganização da estrutura**: criado `scripts/` (run_pipeline, build_dashboard,
  update_pipeline, sync_hermes_models, run_full_pipeline) e `docs/CHANGELOG.md`.
- **v2.2 — Sync Hermes + Auto-update**: `sync_hermes_models.py` monitora
  `provider_models_cache.json` (detecta modelos NIM novos), `update_pipeline.py`
  auto-completo, `run_full_pipeline.py` orquestrador master.
- Cache NVIDIA atualizado p/ 101 modelos; novo #1 = `moonshotai/kimi-k3` (AA=57, ★★★★★, Tier S).
- Cron atualizado para `run_full_pipeline.py --refresh`.

### 22/08/2026 — `@session:default/20260822_124001_fb1dec` + `..._d594ce` — Plano consolidado multi-provider

- **Decisões de escopo confirmadas**:
  1. Providers sem metadados (gemini, kilocode, huggingface, nous, opencode-free)
     → **incluídos marcados N/D, EXCLUÍDOS do ranking CxB**.
  2. Dashboard consolidado **SUBSTITUI** o NVIDIA NIM como único dashboard; `nim_pipeline/`
     permanece como fonte de metadados NVIDIA, mas o dashboard dedicado é arquivado.
- Plano em `.hermes/plans/2026-08-22_120000-multi-provider-consolidated-benchmark.md`.

### 22/08/2026 — `@session:default/20260822_145240_bc6c64` — Implementação do consolidado

- Criado pacote `benchmark_pipe/` (extract → map_source → normalize → enrich → score → build).
- `template_consolidado.html` = novo canônico (marker `//CONSOLIDATED_DATA//`); `dashboard.html` output.
- **Score CxB**: `benefit = ctx(≤40) + tool_call(15) + reasoning(15) + multimodal(10) + AA(≤20)`,
  `cxb = benefit/(cost+1)` (free domina).
- `template.html` arquivado como LEGADO NVIDIA.
- NVIDIA metadata source corrigida → `models_dev_cache.json` do Hermes (102 modelos).
- Novo top: `moonshotai/kimi-k3`; `deepseek-v4-flash-0731` no #7. 82 testes.

### 22/08/2026 — `@session:default/20260822_195826_176d80` — Normalização de nomes (dedup)

- **Problema**: mesmo modelo lógico duplicado (GLM-5.2 em 3 ofertas distintas;
  deepseek-v4-flash 2x no mesmo provider com preços contraditórios).
- **Solução**: `canonicalize()` (alias vendor `deepseek`→`deepseek-ai`, `zai-org`→`z-ai`,
  sufixo `:free`/`:batch`/`:nitro`, equivalência `...flash`↔`...flash-0731`) +
  `dedup_models()` intra-provider (provider + canónico + variante).
- Regra do usuário: **o mesmo provider não disponibiliza o mesmo modelo duplicado** —
  erro de fonte primária. Preservar `aliases`/`divergences` (não perder a verdade).
- Winner prioriza o ID exato do Hermes (rank_key 2/1/0).

### 22/08/2026 — `@session:default/20260822_202714_51c5b5` — "Dados hardcoded" → transparência de custo

- Problema: modelos NVIDIA mostravam preço de tabela + FREE, parecendo contradição.
- Regra já existia (`ALL_FREE_PROVIDERS` nvidia → custo efetivo ZERO). O que faltava era clareza.
- **Solução**: coluna `Custo` única fundindo `is_free`+`price_in`+`source`:
  badge `FREE` (efetivo) + `tabela $X` (referência models.dev) + `⚠ cross` (metadado
  herdado de outro provider) / `⚠ inv.` (só ID do Hermes). Zero mudança em normalize/score/build.

### 23/08/2026 — `@session:default/20260823_093731_5e207a` — Enriquecimento AA Data API v2

- **Novo `benchmark_pipe/aa_api.py`**: bulk fetch `GET /api/v2/language/models/free?page=N&page_size=200`
  (1-4 calls/ciclo, 616 modelos), cache `data/aa_models_raw.json` TTL 24h (= quota Free).
- `enrich_unified()` prioriza **mapa AA API > curado**; propaga AA para variantes de
  do mesmo modelo. Key `AA_API_KEY_benchmark_geral` (env ou `.env`).
- **620% mais cobertura AA**: ~8 → **702/1032 ranked com AA index (68%)**.
- 110 testes pytest. `.gitignore` +aa_models_raw/.env/.hermes/hermes_inventory_bruto.

### 15-23/08 → 23/08/2026 (esta sessão) — Organização + Documentação + Push

- README reescrito para o consolidado multi-provider (estava desatualizado no NVIDIA legado).
- CHANGELOG **v2.3.0** documentando toda a sessão.
- `.gitignore` ampliado (`.hermes/`, `hermes_inventory_bruto.*`).
- Commit `831cab2` + push `main`; branch `gh-pages` preparada com `index.html` na raiz
  (deploy pronto).
- **Blockers**: GitHub Pages não ativável no repo privado (plano Free exige repo público
  ou pago) — usuário optou por não publicar por enquanto.

---

## Decisões duráveis do usuário (não esquecer)

1. **Fonte de verdade metadados NVIDIA** = `~/AppData/Local/hermes/models_dev_cache.json`
   (102 modelos), NÃO `data/nvidia_models_raw.json` (cache stale pode faltar kimi-k3).
2. **Mesmo provider + mesmo modelo lógico = 1 linha** (dedup intra-provider obrigatório).
3. **FREE ≠ melhor** — é "mais custo-benefício" (cost=0 domina, ε=1).
4. **AA index sozinho NÃO rankeia** — exige ctx OU tool_call.
5. **Dashboard é asset versionado** — reproducibilidade via caches locais + pytest gate.
6. **Assinatura obrigatória**: footer link `https://inovatudo.com` `target="_blank" rel="noopener"`.
7. **Economia de tokens**: preferir bulk (AA 4 calls/ciclo), cache TTL = quota, caches locais
   antes de API.