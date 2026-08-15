"""Configuração de path para os testes — garante que nim_pipeline é importável."""

import sys
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path para que `nim_pipeline` e `build_dashboard`
# sejam importáveis independentemente do diretório de execução do pytest.
BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))