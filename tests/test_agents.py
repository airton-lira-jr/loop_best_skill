"""Tests for loopforge.agents.builder (Task 7)."""

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from loopforge.agents.builder import build_agents
from loopforge.config import AppConfig
from loopforge.state import JudgeVerdict, SkillArtifact, SkillPlan

CFG = AppConfig.model_validate({
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
})


def test_build_agents_cria_os_quatro():
    """build_agents retorna AgentsBundle com os 4 agentes."""
    bundle = build_agents(CFG)
    assert {"discovery", "plan", "write", "judge"} <= set(vars(bundle))
    assert isinstance(bundle.discovery, Agent)
    assert isinstance(bundle.plan, Agent)
    assert isinstance(bundle.write, Agent)
    assert isinstance(bundle.judge, Agent)


@pytest.mark.anyio
async def test_plan_agent_produz_skillplan_tipado():
    """Agente plan com TestModel produz saída tipada SkillPlan."""
    bundle = build_agents(CFG)
    with bundle.plan.override(model=TestModel()):
        res = await bundle.plan.run("planeje uma skill")
    assert isinstance(res.output, SkillPlan)


@pytest.mark.anyio
async def test_write_e_judge_produzem_tipos():
    """Agentes write e judge com TestModel produzem SkillArtifact e JudgeVerdict."""
    bundle = build_agents(CFG)
    with bundle.write.override(model=TestModel()):
        w = await bundle.write.run("escreva")
    with bundle.judge.override(model=TestModel()):
        j = await bundle.judge.run("avalie")
    assert isinstance(w.output, SkillArtifact)
    assert isinstance(j.output, JudgeVerdict)
