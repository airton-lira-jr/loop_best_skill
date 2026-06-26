"""Testes da fábrica de tools de web search (loopforge.websearch)."""

from __future__ import annotations

import pytest

from loopforge.config import AppConfig
from loopforge.websearch import construir_websearch_tools

_BASE = {
    "agents": {
        "discovery": {"model": "test:a"},
        "plan": {"model": "test:b"},
        "write": {"model": "test:c"},
        "judge": {"model": "test:d"},
    },
    "skill": {"objetivo": "x"},
}


def _cfg(websearch: dict | None = None) -> AppConfig:
    dados = dict(_BASE)
    if websearch is not None:
        dados = {**_BASE, "websearch": websearch}
    return AppConfig.model_validate(dados)


def test_default_liga_duckduckgo_p_todos_agentes() -> None:
    cfg = _cfg()
    assert cfg.websearch.provider == "duckduckgo"
    for ag in ("discovery", "plan", "write", "judge"):
        tools = construir_websearch_tools(cfg, ag)
        assert len(tools) == 1
        assert tools[0].name == "duckduckgo_search"


def test_agente_fora_da_lista_nao_recebe_tool() -> None:
    cfg = _cfg({"agentes": ["discovery"]})
    assert len(construir_websearch_tools(cfg, "discovery")) == 1
    assert construir_websearch_tools(cfg, "plan") == []
    assert construir_websearch_tools(cfg, "judge") == []


def test_desabilitado_nao_da_tool_a_ninguem() -> None:
    cfg = _cfg({"habilitado": False})
    for ag in ("discovery", "plan", "write", "judge"):
        assert construir_websearch_tools(cfg, ag) == []


def test_tavily_sem_key_omite_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    cfg = _cfg({"provider": "tavily"})
    assert construir_websearch_tools(cfg, "discovery") == []


def test_tavily_com_key_da_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("tavily")  # dep opcional; só roda se instalada
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key-123")
    cfg = _cfg({"provider": "tavily"})
    tools = construir_websearch_tools(cfg, "discovery")
    assert len(tools) == 1
    assert "tavily" in tools[0].name.lower()


def test_tavily_com_key_mas_sem_dep_degrada(monkeypatch: pytest.MonkeyPatch) -> None:
    # provider tavily + key presente, mas dep ausente => [] (não crasha o build).
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key-123")
    cfg = _cfg({"provider": "tavily"})
    try:
        import tavily  # noqa: F401
    except ImportError:
        assert construir_websearch_tools(cfg, "discovery") == []


def test_agentes_invalidos_falham_na_validacao() -> None:
    with pytest.raises(Exception):
        _cfg({"agentes": ["discovery", "naoexiste"]})
