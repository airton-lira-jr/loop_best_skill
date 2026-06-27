"""Testes do delay por agente e do resumo de logs (loopforge.graph)."""

import time

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from loopforge.agents.builder import build_agents
from loopforge.config import AppConfig
from loopforge.graph import _executar_agente, _resumir

CFG_BASE = {
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
    "websearch": {"habilitado": False},
}


def test_delay_default_e_zero():
    """Sem declarar no YAML, delay_segundos de cada agente é 0.0."""
    cfg = AppConfig.model_validate(CFG_BASE)
    assert cfg.agents.discovery.delay_segundos == 0.0
    assert cfg.agents.judge.delay_segundos == 0.0


def test_delay_negativo_rejeitado():
    """delay_segundos negativo levanta ValidationError (ge=0)."""
    dados = {**CFG_BASE, "agents": {**CFG_BASE["agents"]}}
    dados["agents"]["discovery"] = {"model": "x:y", "delay_segundos": -1.0}
    with pytest.raises(ValidationError):
        AppConfig.model_validate(dados)


def test_resumir_trunca_texto_longo():
    """_resumir corta texto acima do limite e indica quantos chars sobraram."""
    assert _resumir("abc", 10) == "abc"
    out = _resumir("a" * 100, 10)
    assert out.startswith("a" * 10)
    assert "+90 chars" in out


@pytest.mark.anyio
async def test_executar_agente_respeita_delay():
    """Com delay > 0, _executar_agente pausa antes de chamar o LLM."""
    bundle = build_agents(AppConfig.model_validate(CFG_BASE))
    with bundle.discovery.override(model=TestModel()):
        inicio = time.monotonic()
        res = await _executar_agente(bundle.discovery, "discovery", "m:x", "p", 0.2, 1)
        elapsed = time.monotonic() - inicio
    assert elapsed >= 0.18
    assert res.output is not None


@pytest.mark.anyio
async def test_executar_agente_sem_delay_nao_pausa():
    """Com delay 0, não há pausa perceptível antes da chamada."""
    bundle = build_agents(AppConfig.model_validate(CFG_BASE))
    with bundle.discovery.override(model=TestModel()):
        inicio = time.monotonic()
        await _executar_agente(bundle.discovery, "discovery", "m:x", "p", 0.0, 1)
        elapsed = time.monotonic() - inicio
    assert elapsed < 0.15
