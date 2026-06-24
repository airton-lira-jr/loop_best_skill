"""Orquestração de alto nível: carrega config, roda o grafo, grava a skill."""

from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from loopforge.config import load_config
from loopforge.context import build_contexto
from loopforge.graph import build_graph
from loopforge.logging import get_logger
from loopforge.persistence import gravar_skill
from loopforge.state import Contexto, LoopState

log = get_logger("runner")


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

    with SqliteSaver.from_conn_string(str(runs_dir / "loopforge.sqlite")) as checkpointer:
        graph = build_graph(config, checkpointer=checkpointer)
        bruto = await graph.ainvoke(
            estado_inicial, config={"configurable": {"thread_id": "run"}}
        )

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
