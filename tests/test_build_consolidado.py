"""Tests for benchmark_pipe.build"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from benchmark_pipe.build import MARKER, build_dashboard
from benchmark_pipe.normalize import UnifiedModel

ROOT = Path(__file__).parent.parent
TEMPLATE = ROOT / "template_consolidado.html"


def _sample_ranked():
    return [
        UnifiedModel(
            provider="nvidia",
            model_id="a/b",
            display_name="a/b",
            context_k=256,
            tool_call=True,
            reasoning=True,
            multimodal=False,
            is_free=True,
            aa_index=50,
            cxb_score=62.5,
            source="models.dev",
        ),
        UnifiedModel(
            provider="openrouter",
            model_id="c/d",
            display_name="c/d",
            context_k=128,
            tool_call=None,
            reasoning=None,
            multimodal=False,
            is_free=False,
            price_in=2.5,
            price_out=10.0,
            aa_index=None,
            cxb_score=8.1,
            source="openrouter-api",
        ),
    ]


def _sample_nd():
    return [UnifiedModel(provider="gemini", model_id="gemini-3-pro", source="hermes-cache-only")]


def test_build_replaces_marker(tmp_path):
    out = tmp_path / "dash.html"
    build_dashboard(_sample_ranked(), _sample_nd(), TEMPLATE, out)
    html = out.read_text(encoding="utf-8")
    assert MARKER not in html
    assert '"ranked"' in html
    assert '"non_ranked"' in html
    assert '"kpis"' in html


def test_build_preserves_signature_footer(tmp_path):
    out = tmp_path / "dash.html"
    build_dashboard(_sample_ranked(), _sample_nd(), TEMPLATE, out)
    html = out.read_text(encoding="utf-8")
    assert 'class="site-footer"' in html
    assert 'href="https://inovatudo.com"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener"' in html


def test_build_includes_free_first(tmp_path):
    out = tmp_path / "dash.html"
    build_dashboard(_sample_ranked(), _sample_nd(), TEMPLATE, out)
    html = out.read_text(encoding="utf-8")
    # primeiro do ranking deve ser o free (cxb 62.5 > 8.1)
    m = re.search(r'"ranked":\s*\[\s*\{[^}]*"model_id":\s*"([^"]+)"', html)
    assert m, "ranked[0] não encontrado"
    assert m.group(1) == "a/b"


def test_build_kpis_counted(tmp_path):
    out = tmp_path / "dash.html"
    build_dashboard(_sample_ranked(), _sample_nd(), TEMPLATE, out)
    html = out.read_text(encoding="utf-8")
    assert '"total_ranked": 2' in html
    assert '"total_inventory": 3' in html
    assert '"free_ranked": 1' in html


def test_build_missing_marker_raises(tmp_path):
    bad_tpl = tmp_path / "bad.html"
    bad_tpl.write_text("<html>no marker</html>", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Marker"):
        build_dashboard(_sample_ranked(), _sample_nd(), bad_tpl, tmp_path / "x.html")


def test_build_idempotent(tmp_path):
    out1 = tmp_path / "a.html"
    out2 = tmp_path / "b.html"
    build_dashboard(_sample_ranked(), _sample_nd(), TEMPLATE, out1)
    build_dashboard(_sample_ranked(), _sample_nd(), TEMPLATE, out2)
    assert out1.read_bytes() == out2.read_bytes()
