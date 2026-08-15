# Modelos Disponíveis — NVIDIA NIM

> **Fonte:** `GET https://integrate.api.nvidia.com/v1/models` (API live em tempo real)
> **Data da consulta:** 14/08/2026
> **Total de modelos:** 102
> **API key:** Configurada no `.env` do Hermes (`providers.nvidia`)
> **Modelo padrão atual:** `z-ai/glm-5.2`

---

## Sumário por Provedor

| Provedor | Qtd | Modelos |
|----------|-----|---------|
| NVIDIA | 44 | Ver seção dedicada abaixo |
| Meta | 11 | Llama 3.x, CodeLlama, Llama2, Muse |
| Google | 9 | Gemma, CodeGemma, DePlot, DiffusionGemma |
| IBM | 4 | Granite 3.0 / 34b / 8b |
| DeepSeek | 2 | Coder 6.7B, V4 Flash |
| Mistral AI | 6 | Mistral Large, Codestral, Mixtral, Nemotron |
| Microsoft | 3 | Kosmos-2, Phi-3, Phi-3.5 |
| Writer | 4 | Palmyra Creative/Fin/Med |
| OpenAI | 2 | GPT-OSS 120B/20B |
| 01-ai | 1 | Yi-Large |
| Adept | 1 | Fuyu-8B |
| AI21 Labs | 1 | Jamba-1.5-Large |
| AI Singapore | 1 | Sea-Lion-7B |
| BAAI | 1 | BGE-M3 (embedding) |
| BigCode | 1 | StarCoder2-15B |
| Databricks | 1 | DBRX-Instruct |
| MiniMax | 1 | MiniMax-M3 |
| Moonshot AI | 1 | Kimi-K2.6 |
| NV-MistralAI | 1 | Mistral-Nemo-12B |
| Poolside | 1 | Laguna-XS-2.1 |
| Snowflake | 1 | Arctic-Embed-L (embedding) |
| StepFun | 1 | Step-3.7-Flash |
| Thinking Machines | 1 | Inkling |
| Z.ai | 1 | GLM-5.2 |
| Zyphra | 1 | Zamba2-7B |

---

## Listagem Completa (102 modelos)

### NVIDIA — Nemotron, NeMo, Embeddings, Riva, Cosmos (44 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `nvidia/ai-synthetic-video-detector` | Detection |
| 2 | `nvidia/cosmos-reason2-8b` | Vision/Reasoning |
| 3 | `nvidia/embed-qa-4` | Embedding |
| 4 | `nvidia/ising-calibration-1.5-31b` | Specialized |
| 5 | `nvidia/llama-3.1-nemoguard-8b-content-safety` | Guardrail |
| 6 | `nvidia/llama-3.1-nemoguard-8b-topic-control` | Guardrail |
| 7 | `nvidia/llama-3.1-nemotron-51b-instruct` | LLM (Nemotron) |
| 8 | `nvidia/llama-3.1-nemotron-70b-instruct` | LLM (Nemotron) |
| 9 | `nvidia/llama-3.1-nemotron-nano-8b-v1` | LLM (Nemotron Nano) |
| 10 | `nvidia/llama-3.1-nemotron-nano-vl-8b-v1` | Vision (VL) |
| 11 | `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` | Guardrail |
| 12 | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | LLM (Nemotron Ultra) |
| 13 | `nvidia/llama-3.2-nemoretriever-1b-vlm-embed-v1` | Embedding/VLM |
| 14 | `nvidia/llama-3.2-nv-embedqa-1b-v1` | Embedding |
| 15 | `nvidia/llama-3.3-nemotron-super-49b-v1` | LLM (Nemotron Super) |
| 16 | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | LLM (Nemotron Super) |
| 17 | `nvidia/llama-nemotron-embed-1b-v2` | Embedding |
| 18 | `nvidia/llama-nemotron-embed-vl-1b-v2` | Embedding/VLM |
| 19 | `nvidia/llama3-chatqa-1.5-70b` | LLM (ChatQA) |
| 20 | `nvidia/mistral-nemo-minitron-8b-8k-instruct` | LLM (Minitron) |
| 21 | `nvidia/nemoretriever-parse` | Retrieval |
| 22 | `nvidia/nemotron-3-embed-1b` | Embedding |
| 23 | `nvidia/nemotron-3-nano-30b-a3b` | LLM (Nemotron 3 Nano) |
| 24 | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | LLM (Reasoning) |
| 25 | `nvidia/nemotron-3-super-120b-a12b` | LLM (Nemotron 3 Super) |
| 26 | `nvidia/nemotron-3-ultra-550b-a55b` | LLM (Nemotron 3 Ultra) |
| 27 | `nvidia/nemotron-3.5-content-safety` | Guardrail |
| 28 | `nvidia/nemotron-3.5-lightning-30b-a3b` | LLM (Lightning) |
| 29 | `nvidia/nemotron-4-340b-instruct` | LLM (Nemotron 4) |
| 30 | `nvidia/nemotron-4-340b-reward` | Reward Model |
| 31 | `nvidia/nemotron-mini-4b-instruct` | LLM (Mini) |
| 32 | `nvidia/nemotron-nano-12b-v2-vl` | Vision (VL) |
| 33 | `nvidia/nemotron-nano-3-30b-a3b` | LLM (Nano 3) |
| 34 | `nvidia/nemotron-parse` | Parsing |
| 35 | `nvidia/neva-22b` | Vision (VL) |
| 36 | `nvidia/nv-embed-v1` | Embedding |
| 37 | `nvidia/nv-embedcode-7b-v1` | Embedding (Code) |
| 38 | `nvidia/nv-embedqa-e5-v5` | Embedding (QA) |
| 39 | `nvidia/nv-embedqa-mistral-7b-v2` | Embedding (QA) |
| 40 | `nvidia/nvclip` | Vision (CLIP) |
| 41 | `nvidia/nvidia-nemotron-nano-9b-v2` | LLM (Nano 9B) |
| 42 | `nvidia/riva-translate-4b-instruct` | Translation |
| 43 | `nvidia/riva-translate-4b-instruct-v1.1` | Translation |
| 44 | `nvidia/riva-translate-4b-instruct-v2` | Translation |
| 45 | `nvidia/vila` | Vision (VILA) |

### Meta (11 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `meta/codellama-70b` | Code |
| 2 | `meta/llama-3.1-70b-instruct` | LLM |
| 3 | `meta/llama-3.1-8b-instruct` | LLM |
| 4 | `meta/llama-3.2-11b-vision-instruct` | Vision |
| 5 | `meta/llama-3.2-1b-instruct` | LLM |
| 6 | `meta/llama-3.2-3b-instruct` | LLM |
| 7 | `meta/llama-3.2-90b-vision-instruct` | Vision |
| 8 | `meta/llama-3.3-70b-instruct` | LLM |
| 9 | `meta/llama-guard-4-12b` | Guardrail |
| 10 | `meta/llama2-70b` | LLM |
| 11 | `meta/muse-glimmer-30b` | Generation |

### Google (9 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `google/codegemma-1.1-7b` | Code |
| 2 | `google/codegemma-7b` | Code |
| 3 | `google/deplot` | Vision (Chart) |
| 4 | `google/diffusiongemma-26b-a4b-it` | Diffusion |
| 5 | `google/gemma-2b` | LLM |
| 6 | `google/gemma-3-12b-it` | LLM |
| 7 | `google/gemma-3-4b-it` | LLM |
| 8 | `google/gemma-4-31b-it` | LLM |
| 9 | `google/recurrentgemma-2b` | LLM |

### Mistral AI (6 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `mistralai/codestral-22b-instruct-v0.1` | Code |
| 2 | `mistralai/mistral-7b-instruct-v0.3` | LLM |
| 3 | `mistralai/mistral-large` | LLM |
| 4 | `mistralai/mistral-large-2-instruct` | LLM |
| 5 | `mistralai/mistral-nemotron` | LLM |
| 6 | `mistralai/mixtral-8x22b-v0.1` | LLM (MoE) |

### IBM (4 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `ibm/granite-3.0-3b-a800m-instruct` | LLM |
| 2 | `ibm/granite-3.0-8b-instruct` | LLM |
| 3 | `ibm/granite-34b-code-instruct` | Code |
| 4 | `ibm/granite-8b-code-instruct` | Code |

### DeepSeek (2 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `deepseek-ai/deepseek-coder-6.7b-instruct` | Code |
| 2 | `deepseek-ai/deepseek-v4-flash-0731` | LLM |

### Microsoft (3 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `microsoft/kosmos-2` | Vision |
| 2 | `microsoft/phi-3-vision-128k-instruct` | Vision |
| 3 | `microsoft/phi-3.5-moe-instruct` | LLM (MoE) |

### Writer (4 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `writer/palmyra-creative-122b` | LLM (Creative) |
| 2 | `writer/palmyra-fin-70b-32k` | LLM (Finance) |
| 3 | `writer/palmyra-med-70b` | LLM (Medical) |
| 4 | `writer/palmyra-med-70b-32k` | LLM (Medical) |

### OpenAI (2 modelos)

| # | ID do Modelo | Categoria |
|---|-------------|-----------|
| 1 | `openai/gpt-oss-120b` | LLM |
| 2 | `openai/gpt-oss-20b` | LLM |

### Outros Provedores (1 modelo cada — 17 modelos)

| # | ID do Modelo | Provedor | Categoria |
|---|-------------|----------|-----------|
| 1 | `01-ai/yi-large` | 01-ai | LLM |
| 2 | `adept/fuyu-8b` | Adept | Vision |
| 3 | `ai21labs/jamba-1.5-large-instruct` | AI21 Labs | LLM (SSM) |
| 4 | `aisingapore/sea-lion-7b-instruct` | AI Singapore | LLM |
| 5 | `baai/bge-m3` | BAAI | Embedding |
| 6 | `bigcode/starcoder2-15b` | BigCode | Code |
| 7 | `databricks/dbrx-instruct` | Databricks | LLM (MoE) |
| 8 | `minimaxai/minimax-m3` | MiniMax | LLM |
| 9 | `moonshotai/kimi-k2.6` | Moonshot AI | LLM |
| 10 | `nv-mistralai/mistral-nemo-12b-instruct` | NV-MistralAI | LLM |
| 11 | `poolside/laguna-xs-2.1` | Poolside | Code |
| 12 | `snowflake/arctic-embed-l` | Snowflake | Embedding |
| 13 | `stepfun-ai/step-3.7-flash` | StepFun | LLM |
| 14 | `thinkingmachines/inkling` | Thinking Machines | LLM |
| 15 | `z-ai/glm-5.2` | Z.ai | LLM |
| 16 | `zyphra/zamba2-7b-instruct` | Zyphra | LLM (Hybrid SSM) |
| 17 | `nvidia/vila` | NVIDIA | Vision |

---

## Modelos Currently em Uso no Hermes

### Modelo Principal
- `z-ai/glm-5.2` (provider: nvidia)

### Fallback Chain (config.yaml)
1. `moonshotai/kimi-k2.6` (nvidia)
2. `minimaxai/minimax-m3` (nvidia)
3. `deepseek-ai/deepseek-v4-pro` (nvidia) *(não listado na API — pode ser alias/removido)*
4. `deepseek-ai/deepseek-v4-flash` (nvidia) *(listado como `deepseek-ai/deepseek-v4-flash-0731`)*
5. `nvidia/nemotron-3-ultra-550b-a55b` (nvidia)
6. `nvidia/nemotron-3-super-120b-a12b` (nvidia)

### MoA Presets — Modelos de Referência (provider: nvidia)
- `z-ai/glm-5.2`
- `minimaxai/minimax-m3`
- `moonshotai/kimi-k2.6`
- `deepseek-ai/deepseek-v4-pro` *(não listado na API)*
- `deepseek-ai/deepseek-v4-flash` *(listado como `deepseek-ai/deepseek-v4-flash-0731`)*

### Modelos Auxiliares (provider: nvidia)
- `z-ai/glm-5.2` usado em: skills_hub, approval, mcp, title_generation, tts_audio_tags, profile_describer, monitor, moa_reference

---

## Notas

- **Embedding models** (`baai/bge-m3`, `snowflake/arctic-embed-l`, `nvidia/embed-qa-4`, `nvidia/nv-embed-*`, etc.) não são LLMs de chat — são modelos de representação vetorial para busca/RAG.
- **Guardrail models** (`nvidia/llama-3.1-nemoguard-*`, `nvidia/llama-3.1-nemotron-safety-guard-*`, `meta/llama-guard-4-12b`, `nvidia/nemotron-3.5-content-safety`) são filtros de segurança, não modelos conversacionais.
- **Reward models** (`nvidia/nemotron-4-340b-reward`) são para RLHF/avaliação, não para inferência direta.
- **Vision models** (`microsoft/kosmos-2`, `meta/llama-3.2-*-vision-*`, `nvidia/neva-22b`, `nvidia/vila`, `nvidia/nvclip`, `adept/fuyu-8b`, `google/deplot`) aceitam imagens como input.
- **Translation models** (`nvidia/riva-translate-4b-*`) são especializados em tradução, não chat.
- **`deepseek-ai/deepseek-v4-pro`** aparece no config.yaml do Hermes mas não foi listado pela API — pode ter sido removido/renomeado desde a configuração.
- **`deepseek-ai/deepseek-v4-flash`** no config corresponde a `deepseek-ai/deepseek-v4-flash-0731` na API (sufixo de versão).

---

*Documento gerado em 14/08/2026 via consulta live à API `integrate.api.nvidia.com/v1/models`.*
