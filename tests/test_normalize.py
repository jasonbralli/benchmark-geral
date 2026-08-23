"""Tests for benchmark_pipe.normalize"""
from __future__ import annotations

from benchmark_pipe.normalize import (
    UnifiedModel,
    canonicalize,
    dedup_models,
    derive_is_free,
    is_rankable,
    normalize_nvidia,
    normalize_openrouter,
    passthrough_ids,
)

# ---------- canonicalize ----------

def test_canonicalize_base():
    assert canonicalize("z-ai/glm-5.2") == ("z-ai/glm-5.2", "base")


def test_canonicalize_free_variant():
    assert canonicalize("z-ai/glm-5.2:free") == ("z-ai/glm-5.2", "free")


def test_canonicalize_batch_variant():
    assert canonicalize("z-ai/glm-5.2:batch") == ("z-ai/glm-5.2", "batch")


def test_canonicalize_vendor_alias():
    assert canonicalize("deepseek/deepseek-v4-flash") == ("deepseek-ai/deepseek-v4-flash-0731", "base")
    assert canonicalize("zai-org/GLM-5.2") == ("z-ai/glm-5.2", "base")


def test_canonicalize_tilde_strip():
    assert canonicalize("~z-ai/glm-latest") == ("z-ai/glm-latest", "base")


def test_canonicalize_backtick_and_case():
    assert canonicalize("`Z-AI/GLM-5.2`") == ("z-ai/glm-5.2", "base")


def test_canonicalize_equiv_with_variant():
    # deepseek flash sem sufixo + :free deve resolver para o canónico com data
    assert canonicalize("deepseek/deepseek-v4-flash:free") == ("deepseek-ai/deepseek-v4-flash-0731", "free")


# ---------- derive_is_free ----------

def test_nvidia_always_free():
    assert derive_is_free("nvidia", "deepseek-ai/x", 5.0, 5.0) is True


def test_opencode_free_always_free():
    assert derive_is_free("opencode-free", "any/model", None, None) is True


def test_free_suffix_tag():
    assert derive_is_free("openrouter", "vendor/x:free", 0.12, 0.5) is True


def test_zero_zero_pricing():
    assert derive_is_free("openrouter", "vendor/x", 0.0, 0.0) is True


def test_paid_openrouter():
    assert derive_is_free("openrouter", "vendor/x", 0.5, 1.5) is False
    assert derive_is_free("gemini", "gemini-3-pro", None, None) is False


def test_zero_but_none_price_not_free():
    # price_in None -> não pode afirmar gratuito por preço
    assert derive_is_free("openrouter", "vendor/x", None, 0) is False


# ---------- UnifiedModel / is_rankable ----------

def test_is_rankable_with_ctx():
    m = UnifiedModel(provider="p", model_id="a/b", context_k=128)
    assert is_rankable(m) is True


def test_is_rankable_with_tool_call():
    m = UnifiedModel(provider="p", model_id="a/b", tool_call=True)
    assert is_rankable(m) is True


def test_single_aa_not_rankable():
    """AA sozinho não habilita rank — passthrough N/D fica fora (escopo)."""
    m = UnifiedModel(provider="huggingface", model_id="moonshotai/kimi-k3", aa_index=57)
    assert is_rankable(m) is False


def test_not_rankable_when_all_none():
    m = UnifiedModel(provider="p", model_id="a/b")
    assert is_rankable(m) is False


# ---------- normalize_nvidia ----------

def _nv_item():
    return {
        "id": "deepseek-ai/deepseek-v4-flash",
        "name": "V4 Flash",
        "tool_call": True,
        "reasoning": True,
        "attachment": False,
        "open_weights": True,
        "modalities": {"input": ["text"], "output": ["text"]},
        "limit": {"context": 262144},
        "cost": {"input": 0.0, "output": 0.0},
        "release_date": "2026-07-31",
    }


def test_normalize_nvidia_fields():
    out = normalize_nvidia([_nv_item()])
    assert len(out) == 1
    m = out[0]
    assert m.provider == "nvidia"
    assert m.context_k == 256
    assert m.tool_call is True and m.reasoning is True
    assert m.is_free is True  # nvidia em ALL_FREE_PROVIDERS
    assert m.source == "models.dev"
    assert m.canonical_id == "deepseek-ai/deepseek-v4-flash-0731"
    assert m.variant == "base"


def test_normalize_nvidia_skips_missing_id():
    assert normalize_nvidia([{"name": "x"}]) == []


# ---------- normalize_openrouter ----------

def test_normalize_openrouter_pricing_in_usd_per_million():
    items = [{
        "id": "anthropic/claude-4.5",
        "name": "Claude 4.5",
        "context_length": 200000,
        "pricing": {"prompt": "0.000003", "completion": "0.000015"},
    }]
    [m] = normalize_openrouter(items)
    assert m.provider == "openrouter"
    assert m.context_k == 195  # 200000/1024
    assert abs(m.price_in - 3.0) < 1e-6
    assert abs(m.price_out - 15.0) < 1e-6
    assert m.is_free is False
    assert m.canonical_id == "anthropic/claude-4.5"
    assert m.variant == "base"


def test_normalize_openrouter_free_suffix():
    items = [{
        "id": "vendor/x:free",
        "context_length": 128000,
        "pricing": {"prompt": "0", "completion": "0"},
    }]
    [m] = normalize_openrouter(items)
    assert m.is_free is True
    assert m.canonical_id == "vendor/x"
    assert m.variant == "free"


def test_normalize_openrouter_tilde_canonical():
    """~z-ai/glm-latest deve normalizar para z-ai/glm-latest base."""
    items = [{"id": "~z-ai/glm-latest", "context_length": 1048576, "pricing": {"prompt": "0.0000014", "completion": "0.0000044"}}]
    [m] = normalize_openrouter(items)
    assert m.canonical_id == "z-ai/glm-latest"
    assert m.variant == "base"


# ---------- passthrough ----------

def test_passthrough_marks_nvidia_free_but_not_openrouter():
    out = passthrough_ids("nvidia", {"a/b", "c/d"})
    assert all(m.is_free for m in out)
    assert all(m.canonical_id for m in out)
    out2 = passthrough_ids("gemini", {"gemini-3-pro"})
    assert out2[0].is_free is False
    assert out2[0].source == "hermes-cache-only"


# ---------- dedup intra-provider (regressões do relato) ----------

def test_dedup_deepseek_intra_nvidia_collapses():
    """Mesmo provider não pode ter o mesmo modelo lógico duplicado."""
    a = UnifiedModel(provider="nvidia", model_id="deepseek-ai/deepseek-v4-flash", context_k=1024, price_in=0.14, release_date="2026-04-24", source="models.dev")
    b = UnifiedModel(provider="nvidia", model_id="deepseek-ai/deepseek-v4-flash-0731", context_k=976, price_in=0, release_date="2026-07-31", source="models.dev")
    for m in (a, b):
        from benchmark_pipe.normalize import apply_canonical
        apply_canonical(m)
    # hermes inventory só tem o 0731 — ele deve vencer
    out = dedup_models([a, b], hermes_inventory={"nvidia": {"deepseek-ai/deepseek-v4-flash-0731"}})
    assert len(out) == 1
    assert out[0].model_id == "deepseek-ai/deepseek-v4-flash-0731"
    assert "deepseek-ai/deepseek-v4-flash" in out[0].aliases
    assert "context_k" in out[0].divergences or "price_in" in out[0].divergences


def test_dedup_keeps_variant_distinct():
    """z-ai/glm-5.2 e z-ai/glm-5.2:free são variantes distintas — não colapsam."""
    a = UnifiedModel(provider="openrouter", model_id="z-ai/glm-5.2", context_k=1024, price_in=0.966, source="openrouter-api")
    b = UnifiedModel(provider="openrouter", model_id="z-ai/glm-5.2:free", context_k=250, price_in=0, source="openrouter-api")
    for m in (a, b):
        from benchmark_pipe.normalize import apply_canonical
        apply_canonical(m)
    out = dedup_models([a, b])
    assert len(out) == 2
    variants = {m.variant for m in out}
    assert variants == {"base", "free"}


def test_dedup_cross_provider_not_collapsed():
    """Mesmo canónico em providers diferentes não colapsa."""
    a = UnifiedModel(provider="nvidia", model_id="z-ai/glm-5.2", context_k=976, source="models.dev")
    b = UnifiedModel(provider="openrouter", model_id="z-ai/glm-5.2", context_k=1024, source="openrouter-api")
    for m in (a, b):
        from benchmark_pipe.normalize import apply_canonical
        apply_canonical(m)
    out = dedup_models([a, b])
    assert len(out) == 2


def test_dedup_idempotent_single():
    m = UnifiedModel(provider="nvidia", model_id="z-ai/glm-5.2", context_k=976, source="models.dev")
    from benchmark_pipe.normalize import apply_canonical
    apply_canonical(m)
    out = dedup_models([m])
    assert len(out) == 1 and out[0].model_id == "z-ai/glm-5.2"
