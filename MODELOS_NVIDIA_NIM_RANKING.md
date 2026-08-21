# Modelos NVIDIA NIM — Ranking Ordenado por Capacidade

> **Critério de ordenação:** 3 pilares — **Intelligence** (MMLU/MMLU-Pro, GPQA, AIME, MATH), **Agentic** (tool use, SWE-bench, Terminal-Bench, reasoning, context length, instruction following), **Coder** (HumanEval, SWE-bench, LiveCodeBench, code completion)
> **Fonte:** Benchmarks públicos de model cards oficiais, NVIDIA research, Hugging Face, e agregadores third-party (BenchLM, llm-stats, OpenRouter)
> **Data:** 14/08/2026
> **Total:** 102 modelos no NIM (LLMs de chat/instruct rankeados; modelos especializados separados)

---

## 🔥 Tier S — Frontier (Topo absoluto)

Modelos que competem com ou superam modelos proprietários fechados (GPT-5.x, Claude Opus 4.x). Excelência em todos os 3 pilares.

| Rank | Modelo | Intel (MMLU-Pro) | Agentic (SWE-bench Verified) | Coder (SWE-bench Pro / HumanEval) | Context | Notas |
|------|--------|-------------------|------------------------------|-------------------------------------|---------|-------|
| 1 | `thinkingmachines/inkling` | 88.7 Global-MMLU-Lite | 77.6 SWE-Verified | 54.3 SWE-Pro | 1M | Frontier aberto. 97.1% AIME, 63.8 Terminal-Bench. Multimodal. Mantém quality com menos tokens que Nemotron Ultra |
| 2 | `z-ai/glm-5.2` | ~82 MMLU-Pro (GLM-5: 91.7 MMLU) | 62.1 SWE-Pro | 62.1 SWE-Pro, 96.95 HumanEval | 1M | **Modelo padrão Hermes**. 99.2% AIME 2026, 91.2 GPQA-Diamond. Excelente custo-benefício (1/6 do preço de GPT-5.5). AA Index: 51 (★★★★★) |
| 3 | `moonshotai/kimi-k2.6` | ~80+ MMLU | 80.2 SWE-Verified | 58.6 SWE-Pro | 256K | Reposição no MMLU mas coding/agentic elite. 300-agent swarm. Multimodal nativo. Empata GPT-5.5 em coding. AA Index: 43 (★★★★☆) |
| 4 | `nvidia/nemotron-3-ultra-550b-a55b` | 66.6 MMLU-Pro | SWE-bench (top-tier) | 75.1 avg code | 1M | 550B total / 55B active (MoE). Híbrido Mamba/Attention. RULER 1M superior a todos open. Fallback do Hermes. AA Index: 38 (★★★★☆) |
| 5 | `nvidia/nemotron-3-super-120b-a12b` | ~65 MMLU-Pro | SWE-bench competes | LiveCodeBench competitive | 1M | 120B total / 12B active. Supera GPT-OSS-120B na maioria dos benchmarks. 2.2x mais throughput que GPT-OSS-120B. RULER 91.75% vs GPT-OSS 22.30% @ 1M context. AA Index: 26 (★★★☆☆) |
| 6 | `minimaxai/minimax-m3` | BenchLM 68.56/100 (#19/218) | Top-tier agentic | SWE-bench Pro, Terminal-Bench 2.1 — strong | 1M | Coding & agentic frontier. Decomposição autônoma de tarefas. Multimodal. MoA reference no Hermes. AA Index: 44 (★★★★☆) |
| 7 | `openai/gpt-oss-120b` | ~73 MMLU-Pro | SWE-bench 26.0 (mini-agent) | 43.0 SWE / 90+ HumanEval | 128K | OpenAI open-weight. Reasoning forte, bom em coding tasks. Context cai acima de 128K. AA Index: 24 (★★★☆☆) |
| 8 | `poolside/laguna-xs-2.1` | N/D (specialized) | Terminal-Bench competitive | SWE-bench with major jump | 131K | Agentic coding specialist. MoE small-scale. Expected MMLU/Chat limitado — compensa em SWE/Terminal-Bench |
| 9 | `deepseek-ai/deepseek-v4-flash-0731` | ~85 MMLU (est. from V4 family) | 82.7 Terminal-Bench 2.1 | 76.8 HumanEval, 54.4 DeepSWE | 1M | **Modelo atual Hermes (NIM)**. 284B/13B MoE. Sucessor oficial do V4-Flash preview (31/jul/2026). Supera V4-Pro-Preview em agent tasks. AA Index: 50 (★★★★★) |

---

## 🟠 Tier A — Strong (Alta capacidade)

Modelos com forte performance em pelo menos 2 dos 3 pilares. Adequados como backbone de agente ou fallback.

| Rank | Modelo | Intel (MMLU) | Agentic | Coder (HumanEval) | Context | Notas |
|------|--------|--------------|---------|---------------------|---------|-------|
| 10 | `mistralai/mistral-large-2-instruct` | 84.0 MMLU | Tool use supported | 92.0 HumanEval | 128K | Codestral liderança opensource em HumanEval. GSM8K 93.0. Multilingual (80+ idiomas) |
| 11 | `nvidia/nemotron-3.5-lightning-30b-a3b` | N/D (classified as efficiency tier) | Agentic gains over Nano 3 | SWE-bench Verified + Terminal-Bench (NVIDIA-reported) | 1M | Successor to Nemotron 3 Nano. 31.6B total / 3.6B active. Speculative decoding. Não compete em peak accuracy → Tekesk é veloz |
| 12 | `nvidia/nemotron-nano-3-30b-a3b` | N/D (small MoE) | Useful for agent swarms | Coding competent | 1M | 30B / 3B active. Antecessor ao Lightning 3.5. Compute efficiency |
| 13 | `meta/llama-3.3-70b-instruct` | 86.0 MMLU | IFEval 92.1 | Good coding | 128K | Llama 3.3 = 3.1 melhorado no mesmo size. Forte instruction following. English-optimized |
| 14 | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | 88.4 MMLU (Nemotron 70B variant) | Tool use capable | Code capable | 128K | 253B params. NVIDIA post-training sobre Llama 3.1. Forte reasoning |
| 15 | `openai/gpt-oss-20b` | ~68 MMLU-Pro (est.) | Reasoning-focused | Coding capable | 128K | Versão small do GPT-OSS. Otmimizado para agentic e reasoning tasks |
| 16 | `ai21labs/jamba-1.5-large-instruct` | 81.2 MMLU-CoT | Arena Hard 65.4 | N/D | 256K | Híbrido Transformer-Mamba. Long context (256K). Function calling (BFCL) |
| 17 | `mistralai/mistral-nemotron` | N/D | Reasoning + agentic | Code capable | Large | Colab Mistral × NVIDIA. Reasoning emphasis |
| 18 | `nvidia/llama-3.1-nemotron-51b-instruct` | ~80 MMLU (est.) | Tool use | Code capable | 128K | 51B NVIDIA-tuned Llama. Mid-size eficiente |
| 19 | `nvidia/nemotron-4-340b-instruct` | ~85 MMLU (est.) | Instruct-tuned | Code capable | 4K | 340B dense. Gen earlier. Context curto limita uso agentic |
| 20 | `writer/palmyra-creative-122b` | N/D (creative-focused) | N/D | N/D | Large | Especializado em creative writing. Não é agentic/coder — bom para geração criativa |
| 21 | `meta/llama-3.1-70b-instruct` | 82.0 MMLU | Moderate | Good coding | 128K | Base sólida. Llama 3.3 supera em MMLU e IFEval |
| 22 | `01-ai/yi-large` | ~80+ MMLU (est.) | N/D | N/D | 32K | Yi series top. Bilingual (EN/ZH). Context curto |
| 23 | `databricks/dbrx-instruct` | 73.7 MMLU | N/D | Good HumanEval | 32K | 132B MoE. Superou GPT-3.5 em MMLU. Context limita uso agentic |
| 24 | `meta/llama-3.2-90b-vision-instruct` | ~84 MMLU (est.) | Vision + tool use | Code capable | 128K | 90B vision-instruct. Maior modelo vision da família Llama 3.2 |
| 25 | `nvidia/llama-3.3-nemotron-super-49b-v1` | N/D | Reasoning optimized | Code capable | Large | NVIDIA Nemotron Super 49B v1. Híbrido reasoning |

---

## 🟡 Tier B — Mid (Capacidade moderada)

Modelos com capacidade decente em pelo menos 1 pilar. Úteis para tarefas específicas ou inferência mais barata.

| Rank | Modelo | Intel (MMLU) | Agentic | Coder | Context | Notas |
|------|--------|--------------|---------|-------|---------|-------|
| 26 | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | N/D | Improved over v1 | Code capable | Large | Iteração v1.5 do Nemotron Super 49B |
| 27 | `mistralai/mistral-large` | ~80 MMLU (est.) | Moderate | 85+ HumanEval | 32K | Mistral Large original (predecessor do Large-2). Context curto |
| 28 | `nvidia/llama-3.1-nemotron-70b-instruct` | 88.4 MMLU | Moderate | Code capable | 128K | NVIDIA post-train do Llama 3.1 70B. MMLU alto |
| 29 | `mistralai/mixtral-8x22b-v0.1` | ~77 MMLU (est.) | Moderate | 45+ HumanEval | 64K | 8x22B MoE. Predecessor da era MoE. Funcional mas superado |
| 30 | `stepfun-ai/step-3.7-flash` | BenchLM 49.9/100 (#121/216) | Limited | Coding #2 on AI Benchy | 256K | Flash model. Coding surpreendentemente forte (#2 AI Benchy). Intel geral fraca |
| 31 | `nv-mistralai/mistral-nemo-12b-instruct` | ~68 MMLU (est.) | Limited | Code capable | 128K | 12B Mistral-Nemo. Pequeno mas eficiente |
| 32 | `mistralai/codestral-22b-instruct-v0.1` | N/D (code-focused) | N/D | 78+ HumanEval | 32K | Code specialist. Bom em code completion. Não é LLM geral |
| 33 | `google/gemma-4-31b-it` | ~75 MMLU (est.) | Limited | Code capable | 128K | Gemma 4 31B. Maior Gemma. Google open-weight |
| 34 | `google/gemma-3-12b-it` | ~70 MMLU (est.) | Limited | Code capable | 128K | Gemma 3 12B. Mid-size Google |
| 35 | `ibm/granite-3.0-8b-instruct` | ~65 MMLU (est.) | Limited | Moderate | 4K | IBM Granite 8B. Enterprise-focused. Context curto |
| 36 | `ibm/granite-3.0-3b-a800m-instruct` | ~55 MMLU (est.) | Very limited | Limited | 4K | 3B with 800M active. Muito pequeno para agentic |
| 37 | `microsoft/phi-3.5-moe-instruct` | ~75 MMLU (est.) | Moderate | Code capable | 128K | Phi-3.5 MoE. Microsoft small model with MoE. Surpreende para o tamanho |
| 38 | `microsoft/phi-3-vision-128k-instruct` | ~70 MMLU (est.) | Vision + tool use | Code capable | 128K | Phi-3 Vision. Multimodal small |
| 39 | `google/gemma-3-4b-it` | ~60 MMLU (est.) | Very limited | Limited | 128K | Gemma 3 4B. Small model |
| 40 | `nvidia/nemotron-mini-4b-instruct` | ~55 MMLU (est.) | Very limited | Limited | Large | 4B NVIDIA. Pequeno para uso agentic |
| 41 | `meta/llama-3.2-11b-vision-instruct` | ~70 MMLU (est.) | Vision + tool use | Code capable | 128K | 11B vision. Útil para tarefas multimodal leves |
| 42 | `nvidia/nvidia-nemotron-nano-9b-v2` | N/D | N/D | N/D | Large | Nano 9B v2. Novo release. Dados limitados |
| 43 | `nvidia/nemotron-nano-12b-v2-vl` | N/D | Vision | N/D | Large | 12B Vision-Language. Nano VL |
| 44 | `nvidia/nemotron-3-nano-30b-a3b` | N/D | Limited (IFBench 74.2 vs Ultra 81.7) | N/D | 1M | Nano 30B. Pequeno para agentic. Use Lightning 3.5 no lugar |
| 46 | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | N/D | Reasoning mode | N/D | 1M | Omni reasoning variant do Nano 30B |
| 47 | `nvidia/nemotron-nano-3-30b-a3b` | N/D | N/D | N/D | Large | Duplicate listing? Mesmo que nemotron-3-nano-30b-a3b |
| 48 | `zyphra/zamba2-7b-instruct` | N/D | IFEval 69.95 (strong for 7B) | N/D | 131K | 7B híbrido SSM-Transformer. IFEval impressionante para tamanho |
| 49 | `google/gemma-2b` | ~50 MMLU (est.) | None | Very limited | 8K | 2B Gemma. Too small para agentic |
| 50 | `google/recurrentgemma-2b` | ~45 MMLU (est.) | None | Very limited | 8K | Recurrent Gemma. Eficiência extrema. Não para qualidade |
| 51 | `meta/llama-3.2-3b-instruct` | ~60 MMLU (est.) | Very limited | Limited | 128K | 3B Llama. Edge inference |
| 52 | `meta/llama-3.2-1b-instruct` | ~50 MMLU (est.) | None | Very limited | 128K | 1B Llama. Edge device |
| 53 | `nvidia/mistral-nemo-minitron-8b-8k-instruct` | ~60 MMLU (est.) | Very limited | Limited | 8K | 8B Minitron. Context limita |
| 54 | `aisingapore/sea-lion-7b-instruct` | ~55 MMLU (est.) | None | Limited | Large | SEA-Lion 7B. Southeast Asian languages focus |
| 55 | `nvidia/llama3-chatqa-1.5-70b` | ~80 MMLU (est.) | Chat/QA focused | N/D | 128K | 70B ChatQA. QA retrieval-focused, não agentic |

---

## ⚫ Não-Rankeados — Especializados / NLLB / Guardrail / Embedding

Estes modelos **não são LLMs de chat** e não participam do ranking de capacidade. Listados por categoria.

### Guardrails / Safety
| Modelo | Função |
|--------|--------|
| `nvidia/llama-3.1-nemoguard-8b-content-safety` | Content safety filter |
| `nvidia/llama-3.1-nemoguard-8b-topic-control` | Topic control filter |
| `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` | Safety guard v3 |
| `meta/llama-guard-4-12b` | Llama Guard 4 |
| `nvidia/nemotron-3.5-content-safety` | Content safety |
| `nvidia/nemotron-4-340b-reward` | Reward model for RLHF |

### Embeddings
| Modelo | Função |
|--------|--------|
| `baai/bge-m3` | Multilingual embedding |
| `snowflake/arctic-embed-l` | Arctic embedding |
| `nvidia/embed-qa-4` | QA embedding |
| `nvidia/nv-embed-v1` | NV Embed v1 |
| `nvidia/nv-embedcode-7b-v1` | Code embedding 7B |
| `nvidia/nv-embedqa-e5-v5` | QA embedding E5 |
| `nvidia/nv-embedqa-mistral-7b-v2` | QA embedding Mistral |
| `nvidia/llama-3.2-nv-embedqa-1b-v1` | QA embedding 1B |
| `nvidia/llama-3.2-nemoretriever-1b-vlm-embed-v1` | VLM embedding 1B |
| `nvidia/llama-nemotron-embed-1b-v2` | Nemotron embed 1B |
| `nvidia/llama-nemotron-embed-vl-1b-v2` | VL embed 1B |
| `nvidia/nemotron-3-embed-1b` | Nemotron 3 embed 1B |

### Translation / Specialized
| Modelo | Função |
|--------|--------|
| `nvidia/riva-translate-4b-instruct` | Translation |
| `nvidia/riva-translate-4b-instruct-v1.1` | Translation v1.1 |
| `nvidia/riva-translate-4b-instruct-v2` | Translation v2 |
| `nvidia/ising-calibration-1.5-31b` | Ising model calibration |
| `nvidia/ai-synthetic-video-detector` | Synthetic video detection |
| `nvidia/nemoretriever-parse` | Document parsing |
| `nvidia/nemotron-parse` | Document parsing |

### Writer (Domain-Specific)
| Modelo | Domínio | Notas |
|--------|---------|-------|
| `writer/palmyra-fin-70b-32k` | Finance | 70B finance specialist. 32K context |
| `writer/palmyra-med-70b` | Medical | 70B medical specialist |
| `writer/palmyra-med-70b-32k` | Medical | 70B medical, 32K context |

### Outros / Legacy
| Modelo | Notas |
|--------|-------|
| `meta/llama2-70b` | Llama 2 70B. Legacy — superado por 3.x |
| `meta/muse-glimmer-30b` | Muse. Generation specialized |
| `mistralai/mistral-7b-instruct-v0.3` | Mistral 7B v0.3. Small model |
| `mistralai/mixtral-8x22b-v0.1` | Mixtral 8x22B. Predecessor MoE |

---









## 📊 Scorecard — Top 10 por AA Index

Ranking ordenado pelo **Artificial Analysis Intelligence Index v4.1** (score third-party oficial, 0-100). Modelos sem score AA aparecem no final com `N/D`. Calibração: 5★ ≥50 | 4★ ≥35 | 3★ ≥20 | 2★ ≥10 | 1★ <10

| AA Rank | Modelo | AA Index | AA ★ | Tier |
|--------:|--------|---------:|:----:|:----:|
| 1 | `moonshotai/kimi-k3` | 57 | ★★★★★ | S |
| 2 | `z-ai/glm-5.2` | 51 | ★★★★★ | S |
| 3 | `deepseek-ai/deepseek-v4-flash-0731` | 50 | ★★★★★ | S |
| 4 | `minimaxai/minimax-m3` | 44 | ★★★★ | S |
| 5 | `moonshotai/kimi-k2.6` | 43 | ★★★★ | S |
| 6 | `thinkingmachines/inkling` | 41 | ★★★★ | S |
| 7 | `nvidia/nemotron-3-ultra-550b-a55b` | 38 | ★★★★ | S |
| 8 | `nvidia/nemotron-3-super-120b-a12b` | 26 | ★★★ | A |

---

## 📝 Metodologia de Ordenação

### Pilares de Avaliação

Os pilares são compilados a partir de benchmarks públicos (MMLU-Pro, SWE-bench, Terminal-Bench, HumanEval, etc.).

1. **Intelligence** — Capacidade geral de raciocínio e conhecimento
   - Benchmarks: MMLU, MMLU-Pro, GPQA-Diamond, AIME, MATH-500, HLE

2. **Agentic** — Capacidade de tool use, reasoning em múltiplos passos, e orquestração
   - Benchmarks: SWE-bench Verified, Terminal-Bench, Tau-Bench, IFEval, BFCL
   - Métricas secundárias: context length, instruction following, multi-step reasoning

3. **Coder** — Capacidade de geração e compreensão de código
   - Benchmarks: HumanEval, SWE-bench (Pro/Verified/Lite), LiveCodeBench, Terminal-Bench

### Artificial Analysis Intelligence Index (3rd-party)

Para validar as estimativas acima, o dashboard também exibe o **Artificial Analysis Intelligence Index v4.1** — score agregado third-party (0-100) que combina 4 categorias com pesos definidos pela metodologia oficial da AA:

- **Agents (34%)** — AA-Omniscience, Terminal-Bench, SWE-bench agentic
- **Coding (24%)** — AA-Coding-Agent Index (DeepSWE, SWE-Atlas-QnA)
- **Scientific Reasoning (24%)** — GPQA-Diamond, MMLU-Pro-Sci
- **General (18%)** — MMLU-Pro, HLE

Calibração de estrelas AA: 5★ ≥50 | 4★ ≥35 | 3★ ≥20 | 2★ ≥10 | 1★ <10

> Fonte: https://artificialanalysis.ai/methodology/intelligence-benchmarking

### Ordenação Hierárquica

1. **Tier S** (Frontier) — Compete com modelos proprietários fechados. Top 3 pilares
2. **Tier A** (Strong) — Forte em 2+ pilares. Adequado como backbone de agente
3. **Tier B** (Mid) — Decente em 1+ pilar. Útil para tarefas específicas
4. **Não-Rankeados** — Embeddings, Guardrails, Translation, Reward models, Parsing, Legacy

> **Tier C (Code Specialist) e Tier D (Vision/VLM) foram removidos** — modelos especializados de 2023-2024 que não competem com os LLMs de chat/instruct atuais.

### Notas

- **`deepseek-ai/deepseek-v4-flash`** no config do Hermes corresponde ao checkpoint **V4-Flash-0731** na API NIM (publicado 31/jul/2026). O nome e base URL não mudaram. V4-Flash-0731 **não é alias** do V4-Pro — são modelos distintos, com Flash-0731 superando Pro-Preview em agent tasks (Terminal-Bench 82.7% vs 72.1%).
- Scores marcados com **(est.)** são estimativas baseadas na família do modelo ou predecessor, quando benchmarks públicos exatos não foram encontrados.
- Benchmarks self-reported (vendor) vs third-party: o AA Intelligence Index (coluna "AA Index" no dashboard) é a fonte third-party oficial; as estrelas das colunas Intel/Agentic/Coder/Overall podem incluir scores self-reported que tendem a ser otimistas.
- Modelos muito novos (Lightning 3.5 de 11/08/2026, Inkling de ~07/08/2026) têm menos dados third-party.

---

*Documento atualizado em 14/08/2026. Scores compilados de: NVIDIA research papers, Hugging Face model cards, BenchLM.ai, llm-stats.com, OpenRouter, tokencalculator.com, Artificial Analysis Intelligence Index v4.1, e publicações especializadas.*
