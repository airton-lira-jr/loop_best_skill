"""Tests for loopforge.agents.builder (Task 7)."""

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

from loopforge.agents.builder import _resolver_modelo, build_agents
from loopforge.config import AppConfig
from loopforge.state import DiscoveryReport, JudgeVerdict, SkillArtifact, SkillPlan

CFG = AppConfig.model_validate({
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
    # websearch off: TestModel chama toda tool automaticamente; com a tool de
    # busca ligada isso viraria request real à rede e quebraria a hermeticidade.
    "websearch": {"habilitado": False},
})


def test_resolver_modelo_repassa_provider_nativo():
    """Prefixos nativos do PydanticAI são repassados como string, sem tocar."""
    assert _resolver_modelo("anthropic:claude-opus-4-8") == "anthropic:claude-opus-4-8"
    assert _resolver_modelo("openrouter:qwen/qwen3-coder:free") == "openrouter:qwen/qwen3-coder:free"


def test_resolver_modelo_nvidia_monta_openai_chat_model(monkeypatch):
    """Prefixo nvidia: vira OpenAIChatModel apontado p/ o endpoint da NVIDIA NIM."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-teste")
    modelo = _resolver_modelo("nvidia:google/gemma-4-31b-it")
    assert isinstance(modelo, OpenAIChatModel)
    assert modelo.model_name == "google/gemma-4-31b-it"
    assert "integrate.api.nvidia.com" in str(modelo.base_url)


def test_resolver_modelo_nvidia_sem_chave_levanta(monkeypatch):
    """Sem NVIDIA_API_KEY, resolver o prefixo nvidia: falha com mensagem clara."""
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        _resolver_modelo("nvidia:google/gemma-4-31b-it")


def test_resolver_modelo_openrouter_sem_chave_repassa_string(monkeypatch):
    """Sem OPENROUTER_API_KEY, openrouter: cai de volta na string (defer nativo)."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert _resolver_modelo("openrouter:qwen/qwen3-coder:free") == "openrouter:qwen/qwen3-coder:free"


def test_resolver_modelo_openrouter_com_chave_e_client_monta_modelo(monkeypatch):
    """Com chave + http_client, openrouter: vira OpenAIChatModel limitado por RPM."""
    import httpx
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    client = httpx.AsyncClient()
    modelo = _resolver_modelo("openrouter:google/gemma-4-31b-it:free", client, max_retries=6)
    assert isinstance(modelo, OpenAIChatModel)
    assert modelo.model_name == "google/gemma-4-31b-it:free"
    assert "openrouter.ai" in str(modelo.base_url)
    # max_retries do config chega no cliente OpenAI subjacente.
    assert modelo._provider.client.max_retries == 6


def test_resolver_modelo_openrouter_com_chave_sem_client_repassa_string(monkeypatch):
    """Sem http_client, openrouter: ainda cai na string (sem rate limit injetado)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    assert _resolver_modelo("openrouter:x/y") == "openrouter:x/y"


def test_build_agents_cria_os_quatro():
    """build_agents retorna AgentsBundle com os 4 agentes."""
    bundle = build_agents(CFG)
    assert {"discovery", "plan", "write", "judge"} <= set(vars(bundle))
    assert isinstance(bundle.discovery, Agent)
    assert isinstance(bundle.plan, Agent)
    assert isinstance(bundle.write, Agent)
    assert isinstance(bundle.judge, Agent)


@pytest.mark.anyio
async def test_discovery_agent_produz_discovery_report_tipado():
    """Agente discovery com TestModel produz saída tipada DiscoveryReport."""
    bundle = build_agents(CFG)
    with bundle.discovery.override(model=TestModel()):
        res = await bundle.discovery.run("faça discovery")
    assert isinstance(res.output, DiscoveryReport)


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


def test_sem_mcp_nenhum_agente_tem_toolset():
    """Sem mcp.config_path, nenhum agente recebe toolsets de usuário."""
    bundle = build_agents(CFG)
    assert bundle.discovery._user_toolsets == []
    assert bundle.judge._user_toolsets == []


def test_mcp_toolsets_so_nos_agentes_configurados(tmp_path):
    """Com mcp.config_path, só os agentes em mcp.agentes ganham as toolsets."""
    mcp_json = tmp_path / "mcp.json"
    mcp_json.write_text(
        '{"mcpServers": {"dummy": {"command": "x", "args": []}}}', encoding="utf-8"
    )
    cfg = AppConfig.model_validate({
        "agents": {
            "discovery": {"model": "google-gla:gemini-2.0-flash"},
            "plan": {"model": "anthropic:claude-opus-4-8"},
            "write": {"model": "anthropic:claude-opus-4-8"},
            "judge": {"model": "google-gla:gemini-2.0-flash"},
        },
        "skill": {"objetivo": "x"},
        "mcp": {"config_path": str(mcp_json), "agentes": ["discovery"]},
        "websearch": {"habilitado": False},
    })
    bundle = build_agents(cfg)
    assert len(bundle.discovery._user_toolsets) == 1   # dummy server
    assert bundle.plan._user_toolsets == []             # fora de mcp.agentes
    assert bundle.judge._user_toolsets == []


def test_websearch_anexa_tool_so_nos_agentes_configurados():
    """Com websearch ligado, só os agentes em websearch.agentes ganham a tool."""
    cfg = AppConfig.model_validate({
        "agents": {
            "discovery": {"model": "google-gla:gemini-2.0-flash"},
            "plan": {"model": "anthropic:claude-opus-4-8"},
            "write": {"model": "anthropic:claude-opus-4-8"},
            "judge": {"model": "google-gla:gemini-2.0-flash"},
        },
        "skill": {"objetivo": "x"},
        "websearch": {"habilitado": True, "provider": "duckduckgo", "agentes": ["discovery"]},
    })
    bundle = build_agents(cfg)  # build é lazy: sem rede
    assert "duckduckgo_search" in bundle.discovery._function_toolset.tools
    assert "duckduckgo_search" not in bundle.plan._function_toolset.tools
    assert "duckduckgo_search" not in bundle.judge._function_toolset.tools
