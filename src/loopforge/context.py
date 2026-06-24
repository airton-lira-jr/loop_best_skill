"""Montagem do contexto herdado injetado nos agentes."""

from __future__ import annotations

from pathlib import Path

from loopforge.config import AppConfig
from loopforge.state import Contexto


def build_contexto(
    config: AppConfig,
    extra_docs: list[str] | None = None,
    extra_links: list[str] | None = None,
) -> Contexto:
    """Funde contexto do YAML com extras da CLI e lê o best_practices SKILL.

    Args:
        config: configuração carregada.
        extra_docs: diretórios de doc passados via `--doc` (estendem o YAML).
        extra_links: URLs passadas via `--link` (estendem o YAML).

    Returns:
        Contexto pronto para injeção nos prompts dos agentes.
    """
    docs = [*config.contexto.docs, *(extra_docs or [])]
    links = [*config.contexto.links, *(extra_links or [])]

    bp_conteudo: str | None = None
    if config.skill.best_practices:
        caminho = Path(config.skill.best_practices)
        if caminho.exists():
            bp_conteudo = caminho.read_text(encoding="utf-8")

    return Contexto(docs=docs, links=links, best_practices_conteudo=bp_conteudo)
