"""Construção dos agentes PydanticAI a partir da configuração."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from loopforge.agents.prompts import DISCOVERY_SYS, JUDGE_SYS, PLAN_SYS, WRITE_SYS
from loopforge.config import AppConfig
from loopforge.state import JudgeVerdict, SkillArtifact, SkillPlan


@dataclass
class AgentsBundle:
    """Conjunto dos 4 agentes do loop."""

    discovery: Agent
    plan: Agent
    write: Agent
    judge: Agent


def build_agents(config: AppConfig) -> AgentsBundle:
    """Cria um Agent PydanticAI por nó, com o modelo do YAML e output tipado.

    Args:
        config: configuração carregada (fornece o ``model`` de cada agente).

    Returns:
        AgentsBundle com discovery/plan/write/judge.

    Note:
        defer_model_check=True adia a resolução do provider/modelo até a 1ª execução,
        permitindo construir os agentes sem as chaves de API presentes (ex: em teste).
        NÃO afeta a validação do output_type.
    """
    return AgentsBundle(
        discovery=Agent(
            config.agents.discovery.model,
            system_prompt=DISCOVERY_SYS,
            defer_model_check=True,
        ),
        plan=Agent(
            config.agents.plan.model,
            system_prompt=PLAN_SYS,
            output_type=SkillPlan,
            defer_model_check=True,
        ),
        write=Agent(
            config.agents.write.model,
            system_prompt=WRITE_SYS,
            output_type=SkillArtifact,
            defer_model_check=True,
        ),
        judge=Agent(
            config.agents.judge.model,
            system_prompt=JUDGE_SYS,
            output_type=JudgeVerdict,
            defer_model_check=True,
        ),
    )
