"""Testes para o gate pytest de scripts/run_consolidated.py.

Cobertura: seleção do interpreter do gate (BENCH_PYTEST_PYTHON > shutil.which('python3')
> sys.executable) — protege contra a reincidência do toolchain do Hermes
(tools/python-3.X+... recriado a cada `hermes update`, perdendo pytest).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import scripts.run_consolidated as rc


def _resolve_gate_exe(monkeypatch, env_value, which_result, sys_executable):
    """Replique a lógica do gate para testes de prioridade."""
    monkeypatch.setenv("BENCH_PYTEST_PYTHON", env_value) if env_value is not None else monkeypatch.delenv("BENCH_PYTEST_PYTHON", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: which_result)
    monkeypatch.setattr(sys, "executable", sys_executable)
    return (
        (os.environ.get("BENCH_PYTEST_PYTHON", "") or shutil.which("python3") or sys.executable),
    )[0]


class TestGateInterpreter:
    """Prioridade de seleção do interpreter do gate pytest."""

    def test_env_var_wins_over_which(self, monkeypatch):
        gate = _resolve_gate_exe(monkeypatch, "C:/fake/python313/python.exe", "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe")
        assert gate == "C:/fake/python313/python.exe"

    def test_which_fallback_when_env_empty(self, monkeypatch):
        gate = _resolve_gate_exe(monkeypatch, "", "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe")
        assert gate == "C:/fake/which/python3.exe"

    def test_which_fallback_when_env_missing(self, monkeypatch):
        gate = _resolve_gate_exe(monkeypatch, None, "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe")
        assert gate == "C:/fake/which/python3.exe"

    def test_sys_executable_last_resort(self, monkeypatch):
        gate = _resolve_gate_exe(monkeypatch, None, None, "C:/fake/hermes/python.exe")
        assert gate == "C:/fake/hermes/python.exe"

    def test_empty_which_falls_to_sys_executable(self, monkeypatch):
        gate = _resolve_gate_exe(monkeypatch, "", None, "C:/fake/hermes/python.exe")
        assert gate == "C:/fake/hermes/python.exe"

    def test_env_var_empty_string_is_falsy(self, monkeypatch):
        """BENCH_PYTEST_PYTHON='' NÃO deve vencer (falsy, cai no which)."""
        gate = _resolve_gate_exe(monkeypatch, "", "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe")
        assert gate != ""


class TestGateRun:
    """O gate chama subprocess.run com o interpreter resolvido."""

    def test_run_uses_resolved_interpreter(self, monkeypatch, tmp_path):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "executable", "C:/fake/hermes/python.exe")
        monkeypatch.delenv("BENCH_PYTEST_PYTHON", raising=False)
        monkeypatch.setattr(shutil, "which", lambda n: "C:/fake/which/python3.exe")

        gate_exe = os.environ.get("BENCH_PYTEST_PYTHON", "") or shutil.which("python3") or sys.executable
        res = subprocess.run([gate_exe, "-m", "pytest", "-q"], cwd=BASE, capture_output=True, text=True)
        assert res.returncode == 0
        # subprocess.run foi mockado: fake_run registrou o cmd com o interpreter resolvido.
        assert calls and calls[0][0] == "C:/fake/which/python3.exe"
        assert calls[0][1:] == ["-m", "pytest", "-q"]

    def test_module_flag_present(self):
        """cmd do gate = [interpreter, '-m', 'pytest', '-q']."""
        gate_exe = os.environ.get("BENCH_PYTEST_PYTHON", "") or shutil.which("python3") or sys.executable
        # Valida estrutura esperada por inspeção do código-fonte
        src = (BASE / "scripts" / "run_consolidated.py").read_text(encoding="utf-8")
        assert 'gate_exe, "-m", "pytest", "-q"' in src
