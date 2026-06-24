"""Grafo LangGraph: nós dos agentes, scoring e controle do loop."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from loopforge.agents.builder import AgentsBundle, build_agents
from loopforge.config import AppConfig
from loopforge.logging import get_logger
from loopforge.scoring.composite import score_composto
from loopforge.scoring.deterministic import score_deterministico
from loopforge.scoring.rubric import score_judge
from loopforge.state import IteracaoRegistro, LoopState

log = get_logger("graph")


def _ctx_texto(state: LoopState) -> str:
    """Serializa o contexto herdado para injetar nos prompts.

    Args:
        state: estado atual do loop.

    Returns:
        String com objetivo, docs, links e best practices concatenados.
    """
    partes = [f"OBJETIVO: {state.objetivo}"]
    if state.contexto.docs:
        partes.append("DOCS (paths): " + ", ".join(state.contexto.docs))
    for fonte in state.contexto.docs_conteudo:
        partes.append(f"--- DOC: {fonte.origem} ---\n{fonte.conteudo}")
    if state.contexto.links:
        partes.append("LINKS (urls): " + ", ".join(state.contexto.links))
    for fonte in state.contexto.links_conteudo:
        partes.append(f"--- LINK: {fonte.origem} ---\n{fonte.conteudo}")
    if state.contexto.best_practices_conteudo:
        partes.append("BEST PRACTICES (Asaas):\n" + state.contexto.best_practices_conteudo)
    return "\n".join(partes)


def decidir_loop(state: LoopState) -> str:
    """Decide o próximo passo do loop.

    Retorna "aprovado" se o score atingiu o mínimo; "para" se atingiu
    max_iteracoes ou estagnou (sem melhora do melhor score por
    no_progress_paciencia iterações); senão "reitera". O histórico já inclui
    a iteração atual como último item.

    Args:
        state: estado atual (usa score_final, iteracao, historico, config.loop).

    Returns:
        "aprovado", "para" ou "reitera".
    """
    loop = state.config.loop
    if state.score_final >= loop.score_minimo:
        return "aprovado"
    if state.iteracao >= loop.max_iteracoes:
        return "para"
    scores = [r.score_final for r in state.historico]
    paciencia = loop.no_progress_paciencia
    if len(scores) > paciencia:
        melhor = max(scores)
        idx_melhor = max(i for i, s in enumerate(scores) if s == melhor)
        iters_sem_melhora = (len(scores) - 1) - idx_melhor
        if iters_sem_melhora >= paciencia:
            return "para"
    return "reitera"


def build_builder(config: AppConfig, agents: AgentsBundle | None = None) -> StateGraph:
    """Monta o StateGraph (sem compilar).

    Args:
        config: configuração.
        agents: bundle de agentes; se None, criado de ``config``.

    Returns:
        StateGraph pronto para compilar.
    """
    agents = agents or build_agents(config)

    async def discovery_node(state: LoopState) -> dict:
        if state.discovery_report:  # roda só na 1ª iteração
            return {}
        res = await agents.discovery.run(f"{_ctx_texto(state)}\n\nFaça o discovery.")
        log.info("discovery_ok", chars=len(res.output))
        return {"discovery_report": res.output}

    async def plan_node(state: LoopState) -> dict:
        prompt = (
            f"{_ctx_texto(state)}\n\nDISCOVERY:\n{state.discovery_report}\n\n"
            f"FEEDBACK DO JUDGE (iteração anterior):\n{state.judge_feedback or '—'}\n\n"
            "Produza/atualize a spec da skill."
        )
        res = await agents.plan.run(prompt)
        log.info("plan_ok", name=res.output.name)
        return {"plan": res.output}

    async def write_node(state: LoopState) -> dict:
        prompt = f"{_ctx_texto(state)}\n\nPLANO:\n{state.plan.model_dump_json()}\n\nEscreva a skill."
        res = await agents.write.run(prompt)
        log.info("write_ok", linhas=res.output.skill_md.count(chr(10)) + 1)
        return {"artifact": res.output}

    async def judge_node(state: LoopState) -> dict:
        prompt = (
            f"{_ctx_texto(state)}\n\nSKILL.md:\n{state.artifact.skill_md}\n\n"
            "Avalie a skill."
        )
        res = await agents.judge.run(prompt)
        verdict = res.output

        det, _ = score_deterministico(state.artifact, config.scoring.deterministico)
        bp_presente = state.contexto.best_practices_conteudo is not None
        jdg = score_judge(verdict, config.scoring.judge, bp_presente)
        final = score_composto(det, jdg, config.scoring.pesos)

        iteracao = state.iteracao + 1
        registro = IteracaoRegistro(
            iteracao=iteracao, score_final=final, score_det=det, score_judge=jdg
        )
        log.info("judge_ok", iteracao=iteracao, score_final=round(final, 4),
                 score_det=round(det, 4), score_judge=round(jdg, 4))
        novo_status = "aprovado" if final >= config.loop.score_minimo else state.status
        return {
            "verdict": verdict,
            "score_det": det,
            "score_judge": jdg,
            "score_final": final,
            "judge_feedback": verdict.feedback_acionavel,
            "iteracao": iteracao,
            "historico": [*state.historico, registro],
            "status": novo_status,
        }

    def _rotear(state: LoopState) -> str:
        decisao = decidir_loop(state)
        if decisao == "reitera":
            return "plan"
        return decisao

    def finalizar_status(state: LoopState) -> dict:
        if state.status == "aprovado":
            return {}
        novo = "max_iter" if state.iteracao >= state.config.loop.max_iteracoes else "estagnado"
        return {"status": novo}

    builder = StateGraph(LoopState)
    builder.add_node("discovery", discovery_node)
    builder.add_node("plan", plan_node)
    builder.add_node("write", write_node)
    builder.add_node("judge", judge_node)
    builder.add_node("finalizar", finalizar_status)

    builder.add_edge(START, "discovery")
    builder.add_edge("discovery", "plan")
    builder.add_edge("plan", "write")
    builder.add_edge("write", "judge")
    builder.add_conditional_edges(
        "judge", _rotear, {"aprovado": "finalizar", "para": "finalizar", "plan": "plan"}
    )
    builder.add_edge("finalizar", END)
    return builder


def build_graph(config: AppConfig, agents: AgentsBundle | None = None, checkpointer=None):
    """Compila o grafo.

    Args:
        config: configuração.
        agents: bundle de agentes (opcional).
        checkpointer: checkpointer LangGraph (ex: SqliteSaver) ou None.

    Returns:
        Grafo compilado, invocável via ``.ainvoke(LoopState(...))``.
    """
    return build_builder(config, agents).compile(checkpointer=checkpointer)
