#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper para push do dashboard consolidado para GitHub Pages.
Executa a lógica sem depender de PowerShell.

Uso: python scripts/push_github.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _run(cmd, **kwargs):
    return subprocess.run(
        cmd, capture_output=True, text=True, errors="replace", **kwargs
    )


def main():
    # Define o diretório do projeto (parent do scripts/)
    PROJETO_DIR = Path(__file__).resolve().parent.parent

    print("Atualizando dashboard consolidado...")

    # Atualiza o dashboard com o mesmo interpretador
    result = _run(
        [sys.executable, "scripts/run_consolidated.py", "--use-cache"],
        cwd=str(PROJETO_DIR),
    )

    if result.returncode != 0:
        print(f"Erro ao atualizar dashboard: {result.stderr.strip()[:300]}")
        return 1

    # Data da coleta
    data = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("Enviando para o GitHub...")

    # O GitHub Pages serve index.html na raiz da branch gh-pages
    # O dashboard.html deve ser copiado/renomeado para index.html na raiz
    # ou o template já gera index.html
    # Aqui assumimos que dashboard.html é o arquivo principal

    # Verifica se index.html já existe na raiz (o GitHub Pages serve da raiz)
    index_path = PROJETO_DIR / "index.html"
    dashboard_path = PROJETO_DIR / "dashboard.html"

    # Copia dashboard.html para index.html (o Pages serve index.html na raiz)
    if dashboard_path.exists():
        import shutil
        shutil.copy2(dashboard_path, index_path)
        print(f"Copiado {dashboard_path.name} -> {index_path.name}")

    # Git add: tracked com mudanças + index.html (artefato gerado, ignorado no git)
    git_add_result = _run(["git", "add", "-u"], cwd=str(PROJETO_DIR))
    _run(["git", "add", "index.html"], cwd=str(PROJETO_DIR))

    if git_add_result.returncode != 0:
        print(f"Erro no git add: {git_add_result.stderr.strip()[:300]}")
        return 1

    commit_result = _run(
        ["git", "commit", "-m", f"dashboard {data}"],
        cwd=str(PROJETO_DIR),
    )

    tem_commit_novo = True
    if commit_result.returncode != 0:
        saida = commit_result.stdout + commit_result.stderr
        if "nothing to commit" in saida:
            print("Sem mudanças para commitar — nada a enviar.")
            tem_commit_novo = False
        else:
            print(f"Erro no git commit: {commit_result.stderr.strip()[:300]}")
            return 1

    if not tem_commit_novo:
        return 0

    # Push: main (histórico) + gh-pages (GitHub Pages serve da raiz da gh-pages)
    # gh-pages tem histórico independente → usa force-with-lease
    pushes = [
        (["git", "push", "origin", "main"], "main"),
        (["git", "push", "--force-with-lease", "origin", "main:gh-pages"], "gh-pages"),
    ]
    for cmd, label in pushes:
        push_result = _run(cmd, cwd=str(PROJETO_DIR))
        if push_result.returncode != 0:
            msg = push_result.stderr.strip()[:300]
            print(f"Erro no git push ({label}): {msg}")
            return 1
        print(f"Push OK: origin {label}")

    print("")
    print("OK - GitHub Pages atualizado em " + data)
    return 0


if __name__ == "__main__":
    sys.exit(main())