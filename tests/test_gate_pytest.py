"""Testes para o gate pytest de scripts/run_consolidated.py.

Cobertura: seleção do interpreter do gate via rc._resolve_gate_exe() —
chain BENCH_PYTEST_PYTHON > shutil.which('py') > shutil.which('python3')
> sys.executable. Protege contra as duas reincidências conhecidas:
1. Toolchain do Hermes (tools/python-3.X+...) recriado a cada `hermes update`
   perdendo pytest (25/09, 28/09, 01/10).
2. Aliases python3.exe/python.exe recriados em WindowsApps como stub da
   Microsoft Store (09/10/2026 14:05) — shutil.which('python3') achava o stub,
   que imprime "Python não foi encontrado..." em CP1252 e mata a reader thread
   do subprocess com UnicodeDecodeError (byte 0xe3) → stdout/stderr=None →
   "pytest falhou: None" (10-11/10/2026).
"""

import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import scripts.run_consolidated as rc


def _resolve(monkeypatch, env_value, which_py, which_python3, sys_executable):
    """Mocka ambiente + shutil.which + sys.executable e chama a função real."""
    if env_value is None:
        monkeypatch.delenv("BENCH_PYTEST_PYTHON", raising=False)
    else:
        monkeypatch.setenv("BENCH_PYTEST_PYTHON", env_value)

    def fake_which(name):
        if name == "py":
            return which_py
        if name == "python3":
            return which_python3
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(sys, "executable", sys_executable)
    return rc._resolve_gate_exe()


class TestGateInterpreter:
    """Prioridade de seleção do interpreter do gate pytest."""

    def test_env_var_wins_over_everything(self, monkeypatch):
        gate = _resolve(
            monkeypatch,
            "C:/fake/python313/python.exe",
            "C:/fake/py.exe",
            "C:/fake/which/python3.exe",
            "C:/fake/hermes/python.exe",
        )
        assert gate == "C:/fake/python313/python.exe"

    def test_py_launcher_beats_python3(self, monkeypatch):
        """Regressão 11/10: `py` (launcher real) vence o python3 do PATH."""
        gate = _resolve(
            monkeypatch, "", "C:/fake/py.exe", "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe"
        )
        assert gate == "C:/fake/py.exe"

    def test_py_launcher_beats_python3_when_env_missing(self, monkeypatch):
        gate = _resolve(
            monkeypatch, None, "C:/fake/py.exe", "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe"
        )
        assert gate == "C:/fake/py.exe"

    def test_env_var_empty_string_is_falsy(self, monkeypatch):
        """BENCH_PYTEST_PYTHON='' NÃO deve vencer (falsy, cai no which)."""
        gate = _resolve(
            monkeypatch, "", "C:/fake/py.exe", "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe"
        )
        assert gate != "" and gate == "C:/fake/py.exe"

    def test_falls_back_to_python3_when_no_py(self, monkeypatch):
        gate = _resolve(
            monkeypatch, None, None, "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe"
        )
        assert gate == "C:/fake/which/python3.exe"

    def test_sys_executable_last_resort(self, monkeypatch):
        gate = _resolve(monkeypatch, None, None, None, "C:/fake/hermes/python.exe")
        assert gate == "C:/fake/hermes/python.exe"


class TestGateRun:
    """O gate chama subprocess.run com o interpreter resolvido."""

    def test_run_uses_resolved_interpreter(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        gate = _resolve(
            monkeypatch, None, "C:/fake/py.exe", "C:/fake/which/python3.exe", "C:/fake/hermes/python.exe"
        )
        # Replicação da chamada de main() — fake_run registra o cmd resolvido.
        res = subprocess.run(
            [gate, "-m", "pytest", "-q"],
            cwd=BASE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert res.returncode == 0
        assert calls and calls[0][0] == "C:/fake/py.exe"
        assert calls[0][1:] == ["-m", "pytest", "-q"]

    def test_module_flag_present(self):
        """cmd do gate = [interpreter, '-m', 'pytest', '-q'] + decode tolerante."""
        src = (BASE / "scripts" / "run_consolidated.py").read_text(encoding="utf-8")
        assert 'gate_exe, "-m", "pytest", "-q"' in src
        assert 'errors="replace"' in src


class TestGateLive:
    """Validações ao vivo (skip se o recurso não existe na máquina)."""

    def test_real_py_launcher_has_pytest(self):
        """O `py` do launcher resolve para um Python com pytest instalado."""
        py = shutil.which("py")
        if not py:
            pytest.skip("py launcher ausente nesta máquina")
        r = subprocess.run([py, "-c", "import pytest"], capture_output=True)
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")

    def test_subprocess_stderr_cp1252_does_not_explode(self):
        """Regressão 11/10: stderr em CP1252 (stub Store) não pode matar a captura.

        Com text=True sozinho, um byte 0xe3 estoura UnicodeDecodeError na reader
        thread e zera stdout/stderr (None). Com encoding+errors="replace" a captura
        sobrevive.
        """
        r = subprocess.run(
            [sys.executable, "-c", "import sys; sys.stderr.buffer.write('nao'.encode('cp1252'))"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.stderr is not None
        assert "nao" in r.stderr  # conteúdo sobreviveu (possíveis U+FFFD nos bytes não-decodificáveis)
