"""Orquestração de alto nível: carrega config, roda o grafo, grava a skill."""

from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from loopforge.agents.builder import AgentsBundle, build_agents
from loopforge.config import load_config
from loopforge.context import build_contexto
from loopforge.graph import build_graph
from loopforge.logging import get_logger
from loopforge.persistence import gravar_skill
from loopforge.state import Contexto, LoopState

log = get_logger("runner")


async def _rodar_grafo(graph, estado_inicial: LoopState, agents: AgentsBundle, usa_mcp: bool):
    """Roda o grafo, abrindo as conexões MCP dos agentes quando necessário.

    Args:
        graph: grafo compilado.
        estado_inicial: estado inicial do loop.
        agents: bundle de agentes (entrado como context manager se houver MCP).
        usa_mcp: se True, entra em cada agente (``async with``) para conectar as
            toolsets MCP antes de rodar e fechá-las ao final.

    Returns:
        Estado bruto (dict) devolvido por ``graph.ainvoke``.
    """
    invoke_cfg = {"configurable": {"thread_id": "run"}}
    if not usa_mcp:
        return await graph.ainvoke(estado_inicial, config=invoke_cfg)

    async with AsyncExitStack() as stack:
        for ag in agents.itens():
            await stack.enter_async_context(ag)
        return await graph.ainvoke(estado_inicial, config=invoke_cfg)


async def run_loop(
    config_path: str | Path,
    extra_docs: list[str] | None = None,
    extra_links: list[str] | None = None,
) -> LoopState:
    """Executa o loop completo a partir de um YAML.

    Carrega a config, monta o contexto herdado, roda o grafo com um
    checkpointer SQLite (memory spine, em ``.loopforge/runs/``) e grava a
    skill resultante se houver artefato.

    Args:
        config_path: caminho do YAML de configuração.
        extra_docs: docs adicionais passados pela CLI (estendem o YAML).
        extra_links: links adicionais passados pela CLI (estendem o YAML).

    Returns:
        Estado final do loop (status aprovado/max_iter/estagnado).
    """
    config = load_config(config_path)
    contexto: Contexto = build_contexto(config, extra_docs, extra_links)

    runs_dir = Path(".loopforge/runs")
    runs_dir.mkdir(parents=True, exist_ok=True)

    estado_inicial = LoopState(
        objetivo=config.skill.objetivo, contexto=contexto, config=config
    )

    agents = build_agents(config)
    usa_mcp = config.mcp.config_path is not None

    with SqliteSaver.from_conn_string(str(runs_dir / "loopforge.sqlite")) as checkpointer:
        graph = build_graph(config, agents=agents, checkpointer=checkpointer)
        bruto = await _rodar_grafo(graph, estado_inicial, agents, usa_mcp)

    final = LoopState.model_validate(bruto)
    if final.artifact is not None:
        nome = final.plan.name if final.plan else "skill"
        destino = gravar_skill(final.artifact, config.skill.output_dir, nome)
        log.info(
            "skill_gravada",
            destino=str(destino),
            status=final.status,
            score_final=round(final.score_final, 4),
        )
    return final
