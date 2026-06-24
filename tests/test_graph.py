"""Testes do grafo LangGraph e da função decidir_loop."""

import pytest
from pydantic_ai.models.test import TestModel

from loopforge.agents.builder import build_agents
from loopforge.config import AppConfig
from loopforge.graph import build_graph, decidir_loop
from loopforge.state import Contexto, IteracaoRegistro, LoopState

CFG = AppConfig.model_validate({
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
    "loop": {"max_iteracoes": 3, "score_minimo": 0.8, "no_progress_paciencia": 2},
})


def _state(**kw):
    base = dict(objetivo="x", contexto=Contexto(), config=CFG)
    base.update(kw)
    return LoopState(**base)


def test_decidir_aprovado():
    assert decidir_loop(_state(score_final=0.85, iteracao=1)) == "aprovado"


def test_decidir_para_no_max_iter():
    assert decidir_loop(_state(score_final=0.5, iteracao=3)) == "para"


def test_decidir_para_por_estagnacao():
    # paciencia=2: melhor score (0.60) atingido há 2 iterações sem melhora → para
    hist = [
        IteracaoRegistro(iteracao=1, score_final=0.60, score_det=0, score_judge=0),
        IteracaoRegistro(iteracao=2, score_final=0.55, score_det=0, score_judge=0),
        IteracaoRegistro(iteracao=3, score_final=0.55, score_det=0, score_judge=0),
    ]
    assert decidir_loop(_state(score_final=0.55, iteracao=3, historico=hist)) == "para"


def test_decidir_reitera():
    # score melhorando, abaixo do mínimo, dentro do limite, sem estagnação → reitera
    hist = [
        IteracaoRegistro(iteracao=1, score_final=0.40, score_det=0, score_judge=0),
        IteracaoRegistro(iteracao=2, score_final=0.60, score_det=0, score_judge=0),
    ]
    assert decidir_loop(_state(score_final=0.60, iteracao=2, historico=hist)) == "reitera"


@pytest.mark.anyio
async def test_grafo_roda_ate_aprovar_com_testmodel():
    # Judge sempre devolve notas altas via TestModel(custom_output_args) → aprova na 1ª volta.
    bundle = build_agents(CFG)
    judge_out = {
        "alinhamento_objetivo": {"nota": 0.95, "rationale": "ok"},
        "discoverability": {"nota": 0.95, "rationale": "ok"},
        "concisao_clareza": {"nota": 0.95, "rationale": "ok"},
        "completude": {"nota": 0.95, "rationale": "ok"},
        "aderencia_best_practices": {"nota": 0.95, "rationale": "ok"},
        "feedback_acionavel": "nada",
    }
    write_out = {
        "skill_md": "---\nname: x\ndescription: Use quando testar.\n---\n# X\n",
        "arquivos": [],
    }
    with bundle.discovery.override(model=TestModel()), \
         bundle.plan.override(model=TestModel()), \
         bundle.write.override(model=TestModel(custom_output_args=write_out)), \
         bundle.judge.override(model=TestModel(custom_output_args=judge_out)):
        graph = build_graph(CFG, agents=bundle)
        final = await graph.ainvoke(LoopState(objetivo="x", contexto=Contexto(), config=CFG))
    assert final["status"] == "aprovado"
    assert final["score_final"] >= 0.8
