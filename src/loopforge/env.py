"""Carregamento das variáveis de ambiente (chaves de API) de um arquivo .env.

As chaves dos providers (``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY``,
``OPENAI_API_KEY``, ...) são lidas pelo PydanticAI a partir do ambiente. Esta
função carrega um ``.env`` para o processo, evitando ter que exportar tudo na
mão a cada execução. Variáveis já presentes no ambiente têm precedência (o
``.env`` não as sobrescreve).
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def carregar_env(dotenv_path: str | Path | None = None) -> None:
    """Carrega variáveis de um arquivo .env para o ambiente do processo.

    Args:
        dotenv_path: caminho do arquivo .env. Se None, procura um ``.env`` no
            diretório atual e nos diretórios pais.
    """
    if dotenv_path is None:
        load_dotenv(override=False)
    else:
        load_dotenv(dotenv_path=str(dotenv_path), override=False)
