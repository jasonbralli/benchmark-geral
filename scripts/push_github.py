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

    # Git add: tracked com mudanças. index.html é gitignored (artefato de gh-pages).
    git_add_result = _run(["git", "add", "-u"], cwd=str(PROJETO_DIR))

    if git_add_result.returncode != 0:
        print(f"Erro no git add: {git_add_result.stderr.strip()[:300]}")
        return 1

    # Commit em main (histórico + código). index.html é artefato gitignored em main.
    commit_result = _run(
        ["git", "commit", "-m", f"dashboard {data}"],
        cwd=str(PROJETO_DIR),
    )

    if commit_result.returncode != 0:
        saida = commit_result.stdout + commit_result.stderr
        if "nothing to commit" in saida:
            print("Sem mudanças no main — seguindo p/ gh-pages mesmo assim.")
        else:
            print(f"Erro no git commit: {commit_result.stderr.strip()[:300]}")
            return 1

    # Push main (histórico/código) — se falhar com "up to date", ok
    push_main = _run(["git", "push", "origin", "main"], cwd=str(PROJETO_DIR))
    if push_main.returncode != 0:
        msg = push_main.stderr.strip()[:300]
        if "up to date" not in msg and "up-to-date" not in msg:
            print(f"Erro no git push (main): {msg}")
            return 1
    print("Push OK: origin main")

    # gh-pages: snapshot orphan contendo APENAS index.html na raiz.
    # Estratégia: cria tree temporária com index.html, commit orphan, push --force.
    # Isto evita herdar o histórico de main (que tem scripts/data/código irrelevantes).
    if not index_path.exists():
        print(f"Erro: {index_path} não existe após cópia.")
        return 1

    # 1) Cria blob do index.html
    blob = _run(["git", "hash-object", "-w", str(index_path)], cwd=str(PROJETO_DIR))
    if blob.returncode != 0:
        print(f"Erro hash-object: {blob.stderr.strip()[:200]}")
        return 1
    blob_sha = blob.stdout.strip()

    # 2) Cria tree temporária com index.html apontando pro blob
    tree = _run(
        ["git", "mktree"],
        input=f"100644 blob {blob_sha}\tindex.html\n",
        cwd=str(PROJETO_DIR),
    )
    if tree.returncode != 0:
        print(f"Erro mktree: {tree.stderr.strip()[:200]}")
        return 1
    tree_sha = tree.stdout.strip()

    # 3) Commit orphan com o tree (sem parent = histórico novo)
    commit_orphan = _run(
        ["git", "commit-tree", tree_sha, "-m", f"gh-pages: dashboard {data}"],
        cwd=str(PROJETO_DIR),
    )
    if commit_orphan.returncode != 0:
        print(f"Erro commit-tree: {commit_orphan.stderr.strip()[:200]}")
        return 1
    orphan_sha = commit_orphan.stdout.strip()

    # 4) Force-push do orphan commit para gh-pages
    push_gh = _run(
        ["git", "push", "--force", "origin", f"{orphan_sha}:refs/heads/gh-pages"],
        cwd=str(PROJETO_DIR),
    )
    if push_gh.returncode != 0:
        print(f"Erro no git push (gh-pages): {push_gh.stderr.strip()[:300]}")
        return 1
    print("Push OK: origin gh-pages (orphan snapshot)")

    print("")
    print("OK - GitHub Pages atualizado em " + data)
    return 0


if __name__ == "__main__":
    sys.exit(main())