"""Construção dos agentes PydanticAI a partir da configuração."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.mcp import load_mcp_toolsets
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import AbstractToolset

from loopforge.agents.prompts import DISCOVERY_SYS, JUDGE_SYS, PLAN_SYS, WRITE_SYS
from loopforge.config import AppConfig
from loopforge.mcp_readonly import filtro_readonly
from loopforge.ratelimit import criar_cliente_rate_limited
from loopforge.state import DiscoveryReport, JudgeVerdict, SkillArtifact, SkillPlan
from loopforge.websearch import construir_websearch_tools

# NVIDIA NIM (build.nvidia.com) é um endpoint OpenAI-compatible. O PydanticAI não
# tem um prefixo `nvidia:` nativo, então tratamos esse prefixo aqui apontando um
# OpenAIChatModel para o endpoint da NVIDIA. A chave vem de NVIDIA_API_KEY (nvapi-...).
NVIDIA_PREFIXO = "nvidia:"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
OPENROUTER_PREFIXO = "openrouter:"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Quantas vezes o PydanticAI reenvia ao modelo quando a SAÍDA não bate o schema
# tipado (output_type). O default do framework é 1 — baixo para modelos abertos
# (Llama/NVIDIA) que erram o JSON de structures aninhadas (ex: JudgeVerdict). Com
# 3, o modelo recebe o erro de validação e tem mais chances de corrigir antes de
# levantar UnexpectedModelBehavior.
RETRIES_OUTPUT = 3

# Temperatura baixa reduz variância do avaliador — sem isso a MESMA skill pode
# passar numa rodada e reprovar noutra só por ruído de amostragem, já que o score
# do Judge pesa 70% do score_final (ver scoring/composite.py). O Write também
# ganha temperatura baixa: deve ser fiel às fontes (achados/spec), não criativo.
# Discovery fica na temperatura default do provider — exploração se beneficia de
# diversidade entre chamadas.
JUDGE_TEMPERATURE = 0.1
WRITE_TEMPERATURE = 0.3


def _async_openai(
    base_url: str, api_key: str, http_client: httpx.AsyncClient | None, max_retries: int
) -> AsyncOpenAI:
    """Monta o cliente OpenAI-compatible com o rate limit e os retries do config.

    O ``http_client`` carrega o rate limit (RPM, ver ``loopforge.ratelimit``);
    ``max_retries`` controla quantas vezes o SDK reenvia ao tomar 429/5xx,
    respeitando o ``Retry-After`` do provider.
    """
    return AsyncOpenAI(
        base_url=base_url, api_key=api_key, http_client=http_client, max_retries=max_retries
    )


def _resolver_modelo(
    model: str, http_client: httpx.AsyncClient | None = None, max_retries: int = 6
) -> str | Model:
    """Resolve a string ``model`` do YAML para o que o ``Agent`` espera.

    Prefixos nativos do PydanticAI (``anthropic:``, ``google-gla:``, ``openai:``,
    ...) são repassados como string — o PydanticAI resolve provider e chave de API
    sozinho.

    Dois prefixos são montados aqui para poder injetar o ``http_client`` (rate
    limit, ver ``loopforge.ratelimit``) e o ``max_retries``:

    - ``openrouter:`` — ``OpenAIChatModel`` + ``OpenRouterProvider`` (a chave vem de
      ``OPENROUTER_API_KEY``). Se a chave ou o ``http_client`` não estiverem
      presentes, cai de volta na string (o PydanticAI resolve nativamente, sem rate
      limit nem os retries custom) — preserva a construção sem chaves (ex: em teste).
    - ``nvidia:`` — NVIDIA NIM (``build.nvidia.com``), endpoint OpenAI-compatible,
      lendo ``NVIDIA_API_KEY``. Ex.: ``nvidia:google/gemma-4-31b-it``.

    Args:
        model: identificador do modelo no formato ``provider:modelo`` do YAML.
        http_client: cliente HTTP (com rate limit) injetado nos providers montados
            aqui. ``None`` desliga a injeção.
        max_retries: retries do SDK em 429/5xx para os modelos montados aqui.

    Returns:
        A própria string (providers nativos / fallback) ou um ``OpenAIChatModel``.

    Raises:
        ValueError: se o prefixo for ``nvidia:`` mas ``NVIDIA_API_KEY`` não
            estiver no ambiente.
    """
    if model.startswith(OPENROUTER_PREFIXO):
        # Só monta o modelo custom (com rate limit + retries) se houver chave E
        # cliente; senão deixa o PydanticAI resolver a string nativamente.
        if os.getenv("OPENROUTER_API_KEY") and http_client is not None:
            nome = model[len(OPENROUTER_PREFIXO):]
            client = _async_openai(
                OPENROUTER_BASE_URL, os.environ["OPENROUTER_API_KEY"], http_client, max_retries
            )
            return OpenAIChatModel(nome, provider=OpenRouterProvider(openai_client=client))
        return model

    if model.startswith(NVIDIA_PREFIXO):
        nome = model[len(NVIDIA_PREFIXO):]
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError(
                f"modelo '{model}' usa NVIDIA NIM mas NVIDIA_API_KEY não está no "
                "ambiente. Defina NVIDIA_API_KEY no .env (chave nvapi-... obtida em "
                "build.nvidia.com)."
            )
        client = _async_openai(NVIDIA_BASE_URL, api_key, http_client, max_retries)
        return OpenAIChatModel(nome, provider=OpenAIProvider(openai_client=client))

    return model


def _precisa_cliente_rate_limited(modelos: list[str]) -> bool:
    """Diz se algum modelo será montado aqui e, portanto, usaria o http_client.

    Espelha exatamente as condições de ``_resolver_modelo``: ``nvidia:`` sempre é
    montado aqui; ``openrouter:`` só quando há ``OPENROUTER_API_KEY``. Evita criar
    um cliente que ficaria sem uso (ex: configs 100% ``anthropic:`` em teste).
    """
    for m in modelos:
        if m.startswith(NVIDIA_PREFIXO):
            return True
        if m.startswith(OPENROUTER_PREFIXO) and os.getenv("OPENROUTER_API_KEY"):
            return True
    return False


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
        não está configurado ou o agente não está em ``mcp.agentes`` (nem é o Judge
        com ``mcp.judge_verificacao`` ligado).
    """
    habilitado = nome in config.mcp.agentes or (
        nome == "judge" and config.mcp.judge_verificacao
    )
    if config.mcp.config_path and habilitado:
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
    modelos = [
        config.agents.discovery.model,
        config.agents.plan.model,
        config.agents.write.model,
        config.agents.judge.model,
    ]
    # Cliente HTTP compartilhado pelos 4 agentes -> o rate limit (RPM) é GLOBAL.
    # Só é criado se algum modelo for montado aqui (openrouter:/nvidia:); configs
    # 100% nativas (ex: anthropic:) não geram cliente ocioso.
    http_client = (
        criar_cliente_rate_limited(config.ratelimit.requisicoes_por_minuto)
        if _precisa_cliente_rate_limited(modelos)
        else None
    )
    http_retries = config.ratelimit.max_retries
    return AgentsBundle(
        discovery=Agent(
            _resolver_modelo(config.agents.discovery.model, http_client, http_retries),
            system_prompt=DISCOVERY_SYS,
            output_type=DiscoveryReport,
            retries=RETRIES_OUTPUT,
            tools=construir_websearch_tools(config, "discovery"),
            toolsets=_toolsets_para(config, "discovery"),
            defer_model_check=True,
        ),
        plan=Agent(
            _resolver_modelo(config.agents.plan.model, http_client, http_retries),
            system_prompt=PLAN_SYS,
            output_type=SkillPlan,
            retries=RETRIES_OUTPUT,
            tools=construir_websearch_tools(config, "plan"),
            toolsets=_toolsets_para(config, "plan"),
            defer_model_check=True,
        ),
        write=Agent(
            _resolver_modelo(config.agents.write.model, http_client, http_retries),
            system_prompt=WRITE_SYS,
            output_type=SkillArtifact,
            retries=RETRIES_OUTPUT,
            tools=construir_websearch_tools(config, "write"),
            toolsets=_toolsets_para(config, "write"),
            model_settings=ModelSettings(temperature=WRITE_TEMPERATURE),
            defer_model_check=True,
        ),
        judge=Agent(
            _resolver_modelo(config.agents.judge.model, http_client, http_retries),
            system_prompt=JUDGE_SYS,
            output_type=JudgeVerdict,
            retries=RETRIES_OUTPUT,
            tools=construir_websearch_tools(config, "judge"),
            toolsets=_toolsets_para(config, "judge"),
            model_settings=ModelSettings(temperature=JUDGE_TEMPERATURE),
            defer_model_check=True,
        ),
    )
