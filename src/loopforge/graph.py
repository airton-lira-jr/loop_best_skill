"""Grafo LangGraph: nós dos agentes, scoring e controle do loop."""

from __future__ import annotations

import asyncio

from langgraph.graph import END, START, StateGraph
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from loopforge.agents.builder import AgentsBundle, build_agents
from loopforge.config import AppConfig
from loopforge.logging import get_logger
from loopforge.scoring.composite import score_composto
from loopforge.scoring.deterministic import score_deterministico
from loopforge.scoring.rubric import score_judge
from loopforge.state import (
    DimensaoNota,
    DiscoveryReport,
    IteracaoRegistro,
    JudgeVerdict,
    LoopState,
)


def _verdict_fallback(motivo: str) -> JudgeVerdict:
    """Veredito de fallback quando o Judge não consegue produzir saída válida.

    Modelos abertos às vezes falham em montar o ``JudgeVerdict`` aninhado mesmo
    após os retries (``UnexpectedModelBehavior``). Em vez de derrubar o loop
    inteiro, devolvemos um veredito com notas zeradas e o motivo no feedback: a
    iteração conta como reprovada, o loop segue (reitera/para) e a skill escrita
    até aqui ainda é gravada no fim.

    Args:
        motivo: descrição curta do erro, para o feedback acionável.

    Returns:
        ``JudgeVerdict`` com todas as dimensões em 0.0.
    """
    zero = DimensaoNota(nota=0.0, rationale=f"Judge falhou: {motivo}")
    return JudgeVerdict(
        alinhamento_objetivo=zero,
        discoverability=zero,
        concisao_clareza=zero,
        completude=zero,
        aderencia_best_practices=zero,
        feedback_acionavel=(
            f"O agente Judge não conseguiu avaliar nesta iteração ({motivo}). "
            "Possíveis causas: modelo instável com saída tipada aninhada ou tool-calling. "
            "Tente um modelo mais robusto no Judge ou desligue o web search dele."
        ),
        problemas_bloqueantes=[f"Judge falhou ao avaliar ({motivo}); nenhuma nota real disponível."],
    )

log = get_logger("graph")


def _discovery_texto(report: DiscoveryReport | None) -> str:
    """Renderiza o relatório de discovery (abordagens + recomendada) para o prompt.

    Args:
        report: relatório do Discovery, ou None se ainda não rodou.

    Returns:
        Texto formatado com as abordagens e a recomendada.
    """
    if report is None:
        return "—"
    linhas = []
    for a in report.abordagens:
        data = f" [{a.data_atualizacao}]" if a.data_atualizacao else ""
        linhas.append(
            f"- {a.nome} (adequação {a.adequacao:.2f}){data}: {a.resumo}"
            f" | prós: {', '.join(a.pros) or '—'} | contras: {', '.join(a.contras) or '—'}"
        )
    abordagens = "\n".join(linhas) or "—"
    achados = "\n".join(f"- {x}" for x in report.achados) or "—"
    fontes = ", ".join(report.fontes) or "—"
    return (
        f"ACHADOS DA PESQUISA:\n{achados}\n"
        f"FONTES: {fontes}\n"
        f"ABORDAGENS:\n{abordagens}\n"
        f"RECOMENDADA: {report.recomendada}\nJUSTIFICATIVA: {report.justificativa}"
    )


def _plan_texto(plan) -> str:
    """Renderiza a spec do Plan (incluindo seções planejadas e notas para o Write).

    Args:
        plan: ``SkillPlan`` produzido pelo Plan.

    Returns:
        Texto formatado com name, description, estrutura, seções, arquivos, notas
        e justificativa — a trilha de decisão que o Write/Judge consomem.
    """
    secoes = "\n".join(f"  - {s}" for s in plan.secoes) or "  —"
    arquivos = ", ".join(plan.arquivos) or "—"
    return (
        f"NAME: {plan.name}\nDESCRIPTION: {plan.description}\n"
        f"ESTRUTURA: {plan.estrutura}\nSEÇÕES PLANEJADAS:\n{secoes}\n"
        f"ARQUIVOS: {arquivos}\nNOTAS PARA O WRITE: {plan.notas_para_write or '—'}\n"
        f"JUSTIFICATIVA: {plan.justificativa}"
    )


def _arquivos_texto(artifact, limite: int = 1500) -> str:
    """Renderiza os arquivos referenciados da skill para o Judge avaliar completude.

    O Judge precisa VER o conteúdo dos arquivos (não só o ``SKILL.md``) para julgar
    completude e se os links batem. O conteúdo de cada arquivo é truncado para não
    estourar o contexto de modelos menores.

    Args:
        artifact: ``SkillArtifact`` escrito pelo Write.
        limite: máximo de chars por arquivo antes de truncar.

    Returns:
        Texto com cada arquivo (caminho + conteúdo truncado), ou "—" se não houver.
    """
    if not artifact.arquivos:
        return "—"
    partes = []
    for f in artifact.arquivos:
        partes.append(f"--- ARQUIVO: {f.caminho} ---\n{_resumir(f.conteudo, limite)}")
    return "\n".join(partes)


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
        partes.append("BEST PRACTICES:\n" + state.contexto.best_practices_conteudo)
    return "\n".join(partes)


def _feedback_texto(verdict: JudgeVerdict) -> str:
    """Renderiza o veredito do Judge como checklist pro Plan/Write endereçarem.

    Separa bloqueantes de sugestões (em vez de só o `feedback_acionavel` cru)
    para o próximo nó ter um checklist verificável em vez de prosa a interpretar.

    Args:
        verdict: veredito estruturado do Judge.

    Returns:
        Texto formatado com problemas bloqueantes, sugestões e o resumo.
    """
    partes = []
    if verdict.problemas_bloqueantes:
        itens = "\n".join(f"- {p}" for p in verdict.problemas_bloqueantes)
        partes.append(f"PROBLEMAS BLOQUEANTES (endereçar TODOS):\n{itens}")
    if verdict.sugestoes:
        itens = "\n".join(f"- {s}" for s in verdict.sugestoes)
        partes.append(f"SUGESTÕES (não bloqueantes):\n{itens}")
    partes.append(f"RESUMO: {verdict.feedback_acionavel}")
    return "\n\n".join(partes)


def _resumir(texto: str, limite: int = 600) -> str:
    """Encurta um texto longo para caber no log sem poluir o terminal.

    Args:
        texto: texto original (prompt ou retorno do agente).
        limite: tamanho máximo antes de truncar.

    Returns:
        O texto inteiro se couber, ou truncado com indicação de quantos chars
        foram cortados.
    """
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    return f"{texto[:limite]}... (+{len(texto) - limite} chars)"


async def _executar_agente(
    agent, nome: str, modelo: str, prompt: str, delay: float, iteracao: int
):
    """Roda um agente logando o estágio, o prompt e respeitando o delay configurado.

    Loga o início do estágio (nome do nó/agente que está executando, o modelo LLM
    dele, iteração, delay e prompt resumido), aplica a pausa ``delay``
    (anti-sobrecarga do provider, ver ``config.agents.<nome>.delay_segundos``) e
    então chama o LLM. O resumo do RETORNO fica a cargo de cada nó, que conhece o
    formato do output.

    Args:
        agent: agente PydanticAI a executar.
        nome: nome do nó/agente que está executando (discovery/plan/write/judge).
        modelo: identificador do LLM daquele agente (``provider:modelo`` do YAML).
        prompt: prompt completo enviado ao agente.
        delay: segundos de pausa antes da chamada (>= 0).
        iteracao: número da iteração atual do loop (para correlacionar os logs).

    Returns:
        O resultado de ``agent.run(prompt)``.
    """
    log.info(
        "estagio_inicio",
        estagio=nome,
        agente=nome,
        modelo=modelo,
        iteracao=iteracao,
        delay_s=delay,
        prompt=_resumir(prompt),
    )
    if delay > 0:
        await asyncio.sleep(delay)
    res = await agent.run(prompt)
    log.info("estagio_fim", estagio=nome, agente=nome, modelo=modelo, iteracao=iteracao)
    return res


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
        if state.discovery_report is not None:  # roda só na 1ª iteração
            return {}
        prompt = f"{_ctx_texto(state)}\n\nFaça o discovery."
        res = await _executar_agente(
            agents.discovery, "discovery", config.agents.discovery.model, prompt,
            config.agents.discovery.delay_segundos, state.iteracao + 1,
        )
        report = res.output
        log.info(
            "discovery_ok",
            abordagens=len(report.abordagens),
            achados=len(report.achados),
            fontes=len(report.fontes),
            recomendada=report.recomendada,
            resumo=_resumir(report.justificativa, 300),
        )
        return {"discovery_report": report}

    async def plan_node(state: LoopState) -> dict:
        prompt = (
            f"{_ctx_texto(state)}\n\nDISCOVERY:\n{_discovery_texto(state.discovery_report)}\n\n"
            f"FEEDBACK DO JUDGE (iteração anterior):\n{state.judge_feedback or '—'}\n\n"
            "Escolha a melhor abordagem e produza/atualize a spec da skill."
        )
        res = await _executar_agente(
            agents.plan, "plan", config.agents.plan.model, prompt,
            config.agents.plan.delay_segundos, state.iteracao + 1,
        )
        plan = res.output
        log.info(
            "plan_ok",
            name=plan.name,
            secoes=len(plan.secoes),
            notas=_resumir(plan.notas_para_write, 150),
            resumo=_resumir(plan.description, 300),
        )
        return {"plan": plan}

    async def write_node(state: LoopState) -> dict:
        budget = config.scoring.deterministico.budget_linhas
        revisao = ""
        if state.artifact is not None:  # reiteração: revisar, não regenerar do zero
            revisao = (
                "\n\nARTEFATO ANTERIOR (revise endereçando o feedback ponto a ponto):\n"
                f"{state.artifact.skill_md}\n\n"
                f"FEEDBACK DO JUDGE:\n{state.judge_feedback or '—'}"
            )
        prompt = (
            f"{_ctx_texto(state)}\n\n"
            f"DISCOVERY:\n{_discovery_texto(state.discovery_report)}\n\n"
            f"PLANO:\n{_plan_texto(state.plan)}\n\n"
            f"ORÇAMENTO DE LINHAS do SKILL.md: {budget}.{revisao}\n\n"
            "Escreva (ou revise) a skill seguindo o contrato do SKILL.md."
        )
        res = await _executar_agente(
            agents.write, "write", config.agents.write.model, prompt,
            config.agents.write.delay_segundos, state.iteracao + 1,
        )
        artifact = res.output
        log.info(
            "write_ok",
            linhas=artifact.skill_md.count(chr(10)) + 1,
            arquivos=len(artifact.arquivos),
            notas=_resumir(artifact.notas_de_escrita, 200),
            resumo=_resumir(artifact.skill_md, 300),
        )
        return {"artifact": artifact}

    async def judge_node(state: LoopState) -> dict:
        prompt = (
            f"{_ctx_texto(state)}\n\n"
            f"PLANO:\n{_plan_texto(state.plan)}\n\n"
            f"SKILL.md:\n{state.artifact.skill_md}\n\n"
            f"ARQUIVOS REFERENCIADOS:\n{_arquivos_texto(state.artifact)}\n\n"
            f"NOTAS DO WRITE:\n{state.artifact.notas_de_escrita or '—'}\n\n"
            "Avalie o conjunto (SKILL.md + arquivos) contra o objetivo e o plano."
        )
        try:
            res = await _executar_agente(
                agents.judge, "judge", config.agents.judge.model, prompt,
                config.agents.judge.delay_segundos, state.iteracao + 1,
            )
            verdict = res.output
        except (UnexpectedModelBehavior, UsageLimitExceeded) as e:
            # Modelo do Judge não conseguiu produzir o veredito tipado mesmo após
            # os retries. Não derruba o loop: usa fallback (notas 0), a iteração
            # conta como reprovada e a skill já escrita é gravada no fim.
            log.warning("judge_falhou", erro=str(e)[:200], iteracao=state.iteracao + 1)
            verdict = _verdict_fallback(type(e).__name__)

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
            "judge_feedback": _feedback_texto(verdict),
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
