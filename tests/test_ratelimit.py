"""Testes do rate limit por minuto (loopforge.ratelimit)."""

import time

import httpx
import pytest

from loopforge.config import AppConfig
from loopforge.ratelimit import _Limiter, criar_cliente_rate_limited


def test_config_default_rpm_e_10():
    """O default de requisicoes_por_minuto é 10 (sem precisar declarar no YAML)."""
    cfg = AppConfig.model_validate({
        "agents": {
            "discovery": {"model": "anthropic:claude-opus-4-8"},
            "plan": {"model": "anthropic:claude-opus-4-8"},
            "write": {"model": "anthropic:claude-opus-4-8"},
            "judge": {"model": "google-gla:gemini-2.0-flash"},
        },
        "skill": {"objetivo": "x"},
    })
    assert cfg.ratelimit.requisicoes_por_minuto == 10
    assert cfg.ratelimit.max_retries == 6


@pytest.mark.anyio
async def test_limiter_espaça_as_chamadas():
    """3 acquires com intervalo de 0.1s gastam pelo menos ~2 intervalos (espaçados)."""
    limiter = _Limiter(rpm=600)  # 60/600 = 0.1s entre chamadas
    inicio = time.monotonic()
    for _ in range(3):
        await limiter.aguardar()
    elapsed = time.monotonic() - inicio
    # 1ª chamada é imediata; 2ª e 3ª esperam ~0.1s cada => ~0.2s no total.
    assert elapsed >= 0.18


def test_criar_cliente_devolve_async_client_com_hook():
    """O cliente é um httpx.AsyncClient com event hook de request (onde o RPM age)."""
    client = criar_cliente_rate_limited(10)
    assert isinstance(client, httpx.AsyncClient)
    assert len(client.event_hooks["request"]) == 1
