"""Construção dos agentes PydanticAI a partir da configuração."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.mcp import load_mcp_toolsets
from pydantic_ai.toolsets import AbstractToolset

from loopforge.agents.prompts import DISCOVERY_SYS, JUDGE_SYS, PLAN_SYS, WRITE_SYS
from loopforge.config import AppConfig
from loopforge.mcp_readonly import filtro_readonly
from loopforge.state import DiscoveryReport, JudgeVerdict, SkillArtifact, SkillPlan
from loopforge.websearch import construir_websearch_tools


@dataclass
class AgentsBundle:
    """Conjunto dos 4 agentes do loop."""

    discovery: Agent
    plan: Agent
    write: Agent
    judge: Agent

    def itens(self) -> tuple[Agent, ...]:
        """Retorna os 4 agentes em ordem (discovery, plan, write, judge)."""
        return (self.discovery, self.plan, self.write, self.judge)


def _toolsets_para(config: AppConfig, nome: str) -> list[AbstractToolset]:
    """Carrega as toolsets MCP para um agente, se ele estiver habilitado.

    As toolsets são carregadas frescas por agente (uma conexão MCP própria por
    agente, sem compartilhar lifecycle). A carga é preguiçosa: não conecta aos
    servers, só monta os objetos — a conexão ocorre quando o agente roda.

    Cada toolset passa pelo guardrail **read-only** (``filtro_readonly``): a
    aplicação só consulta serviços externos via MCP, nunca escreve/altera neles
    (ver ``loopforge.mcp_readonly``). O filtro é fail-closed — tools de escrita,
    execução ou de nome ambíguo nem aparecem para o agente.

    Args:
        config: configuração carregada.
        nome: nome do agente (discovery/plan/write/judge).

    Returns:
        Lista de toolsets MCP (já filtradas para leitura), ou lista vazia se MCP
        não está configurado ou o agente não está em ``mcp.agentes``.
    """
    if config.mcp.config_path and nome in config.mcp.agentes:
        return [ts.filtered(filtro_readonly) for ts in load_mcp_toolsets(config.mcp.config_path)]
    return []


def build_agents(config: AppConfig) -> AgentsBundle:
    """Cria um Agent PydanticAI por nó, com o modelo do YAML e output tipado.

    Quando ``mcp.config_path`` está definido, os agentes listados em
    ``mcp.agentes`` recebem as toolsets MCP e podem chamá-las autonomamente
    durante a execução (ex: consultar Confluence/Jira quando necessário).

    Args:
        config: configuração carregada (fornece o ``model`` de cada agente e o MCP).

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
            output_type=DiscoveryReport,
            tools=construir_websearch_tools(config, "discovery"),
            toolsets=_toolsets_para(config, "discovery"),
            defer_model_check=True,
        ),
        plan=Agent(
            config.agents.plan.model,
            system_prompt=PLAN_SYS,
            output_type=SkillPlan,
            tools=construir_websearch_tools(config, "plan"),
            toolsets=_toolsets_para(config, "plan"),
            defer_model_check=True,
        ),
        write=Agent(
            config.agents.write.model,
            system_prompt=WRITE_SYS,
            output_type=SkillArtifact,
            tools=construir_websearch_tools(config, "write"),
            toolsets=_toolsets_para(config, "write"),
            defer_model_check=True,
        ),
        judge=Agent(
            config.agents.judge.model,
            system_prompt=JUDGE_SYS,
            output_type=JudgeVerdict,
            tools=construir_websearch_tools(config, "judge"),
            toolsets=_toolsets_para(config, "judge"),
            defer_model_check=True,
        ),
    )
