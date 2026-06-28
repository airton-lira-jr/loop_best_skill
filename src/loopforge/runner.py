"""Orquestração de alto nível: carrega config, roda o grafo, grava a skill."""

from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from loopforge.agents.builder import AgentsBundle, build_agents
from loopforge.config import load_config
from loopforge.context import build_contexto, resolver_objetivo
from loopforge.env import carregar_env
from loopforge.graph import build_graph
from loopforge.logging import get_logger
from loopforge.mcp_discovery import preparar_mcp_config
from loopforge.persistence import criar_serde, gravar_run_md, gravar_skill
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
    # recursion_limit = teto de super-steps do LangGraph. Cada iteração gasta 3
    # (plan→write→judge); +discovery +finalizar. Derivamos de max_iteracoes (com
    # folga) para o loop parar pela NOSSA lógica (decidir_loop) e não estourar o
    # default 25 do LangGraph com um GraphRecursionError quando max_iteracoes é alto.
    limite = 3 * estado_inicial.config.loop.max_iteracoes + 10
    invoke_cfg = {"configurable": {"thread_id": "run"}, "recursion_limit": limite}
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
    carregar_env()  # lê .env (chaves de API) antes de resolver os modelos
    config = load_config(config_path)
    contexto: Contexto = build_contexto(config, extra_docs, extra_links)
    objetivo = resolver_objetivo(config.skill.objetivo)

    runs_dir = Path(".loopforge/runs")
    runs_dir.mkdir(parents=True, exist_ok=True)

    estado_inicial = LoopState(
        objetivo=objetivo, contexto=contexto, config=config
    )

    # MCP: usa config_path explícito ou auto-descobre os servers do Claude Code
    # (filtro incluir/excluir, seleção dinâmica por contexto e probe que descarta
    # servers quebrados). contexto+objetivo alimentam a seleção dinâmica.
    mcp_path, eh_temp = await preparar_mcp_config(
        config, contexto=contexto, objetivo=objetivo
    )
    if mcp_path:
        config.mcp.config_path = mcp_path
    agents = build_agents(config)  # carrega as toolsets MCP do arquivo resolvido
    usa_mcp = mcp_path is not None
    if eh_temp:
        Path(mcp_path).unlink(missing_ok=True)  # toolsets já carregadas; não precisa mais

    async with AsyncSqliteSaver.from_conn_string(str(runs_dir / "loopforge.sqlite")) as checkpointer:
        checkpointer.serde = criar_serde()  # registra nossos tipos -> sem WARNINGs de msgpack
        graph = build_graph(config, agents=agents, checkpointer=checkpointer)
        bruto = await _rodar_grafo(graph, estado_inicial, agents, usa_mcp)

    final = LoopState.model_validate(bruto)

    destino = None
    if final.artifact is not None:
        nome = final.plan.name if final.plan else "skill"
        destino = gravar_skill(final.artifact, config.skill.output_dir, nome)
        gravar_run_md(final, destino)  # trilha de raciocínio inspecionável ao lado da skill

    # Resumo final único: por que parou, melhor score atingido, e onde a skill foi
    # gravada. `status` é aprovado/max_iter/estagnado (ver decidir_loop). A skill é
    # SEMPRE gravada se houve artefato, independentemente de ter aprovado ou não.
    melhor = max((r.score_final for r in final.historico), default=final.score_final)
    log.info(
        "resumo_final",
        status=final.status,
        iteracoes=final.iteracao,
        score_final=round(final.score_final, 4),
        melhor_score=round(melhor, 4),
        score_minimo=config.loop.score_minimo,
        skill=str(destino) if destino else "(nenhuma — sem artefato)",
    )
    return final
