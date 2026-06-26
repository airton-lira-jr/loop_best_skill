"""Tools de web search dadas aos agentes (conteúdo atualizado da internet).

A ideia do loop é cada agente combinar o raciocínio da sua LLM com busca na web
para fundamentar a SKILL em conteúdo recente (libs novas, best practices atuais).
Aqui ficam a fábrica que monta a tool conforme o ``provider`` configurado.

Providers:
- ``duckduckgo`` (default): sem API key, usa o pacote ``ddgs``.
- ``tavily``: otimizado p/ agentes; lê ``TAVILY_API_KEY`` do ambiente. Sem a key,
  a tool é omitida (com warning) — o agente segue só com raciocínio.

Os imports dos backends são preguiçosos para não exigir a dep instalada quando o
provider não é usado.
"""

from __future__ import annotations

import os
from typing import Any

from loopforge.config import AppConfig
from loopforge.logging import get_logger

log = get_logger("websearch")


def construir_websearch_tools(config: AppConfig, agente: str) -> list[Any]:
    """Monta a lista de tools de web search para um agente.

    Args:
        config: configuração carregada.
        agente: nome do agente (discovery/plan/write/judge).

    Returns:
        Lista com a tool de busca (0 ou 1 item). Vazia se o web search está
        desligado, o agente não está em ``websearch.agentes``, ou o provider não
        pôde ser inicializado (ex: Tavily sem ``TAVILY_API_KEY``).
    """
    ws = config.websearch
    if not ws.habilitado or agente not in ws.agentes:
        return []

    if ws.provider == "duckduckgo":
        from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool

        return [duckduckgo_search_tool(max_results=ws.max_results)]

    if ws.provider == "tavily":
        key = os.environ.get("TAVILY_API_KEY")
        if not key:
            log.warning("websearch_tavily_sem_key", agente=agente)
            return []
        try:
            from pydantic_ai.common_tools.tavily import tavily_search_tool
        except ImportError:
            # dep opcional ausente: degrada suave em vez de derrubar o build.
            log.warning("websearch_tavily_dep_ausente", agente=agente)
            return []
        return [tavily_search_tool(key)]

    return []
