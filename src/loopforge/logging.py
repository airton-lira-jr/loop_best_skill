"""Configuração de logging estruturado com structlog + rich."""

from __future__ import annotations

import logging

import structlog
from rich.logging import RichHandler


def setup_logging(verbose: bool = False) -> None:
    """Configura structlog sobre o logging padrão com saída Rich.

    Args:
        verbose: se True, nível DEBUG; senão INFO.
    """
    nivel = logging.DEBUG if verbose else logging.INFO
    logging.root.handlers.clear()
    logging.basicConfig(
        level=nivel,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(nivel),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )


def get_logger(nome: str) -> structlog.BoundLogger:
    """Retorna um logger structlog nomeado.

    Args:
        nome: nome do logger (geralmente o nó do grafo).

    Returns:
        Logger estruturado.
    """
    return structlog.get_logger(nome)
