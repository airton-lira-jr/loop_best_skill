"""Rate limit de requisições por minuto (RPM) para os providers de LLM.

Os providers (sobretudo os modelos ``:free`` do OpenRouter) impõem um teto de
requisições por minuto por chave. Um único ``.run()`` de um agente pode disparar
VÁRIAS chamadas HTTP ao provider (o loop de tool-calling do PydanticAI), então o
limite tem que ser aplicado na camada HTTP, não por nó do grafo.

A estratégia é um ``httpx.AsyncClient`` compartilhado por todos os agentes, com um
*event hook* de request que espaça as chamadas. Como o cliente é o mesmo, o teto é
GLOBAL (a soma das chamadas dos 4 nós, incluindo os tool loops) e bate com o limite
por chave do provider.
"""

from __future__ import annotations

import asyncio

import httpx


class _Limiter:
    """Espaça as chamadas para no máximo ``rpm`` por minuto (intervalo fixo).

    Usa um intervalo fixo (``60 / rpm`` segundos) em vez de um token bucket: sem
    rajada, o que é o mais seguro para os limites agressivos dos modelos ``:free``.
    O lock serializa os acquires, então chamadas concorrentes saem espaçadas.
    """

    def __init__(self, rpm: int) -> None:
        self._intervalo = 60.0 / max(1, rpm)
        self._lock = asyncio.Lock()
        self._proximo = 0.0

    async def aguardar(self) -> None:
        """Bloqueia até que seja permitido fazer a próxima requisição."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            agora = loop.time()
            espera = self._proximo - agora
            if espera > 0:
                await asyncio.sleep(espera)
                agora = loop.time()
            self._proximo = agora + self._intervalo


def criar_cliente_rate_limited(rpm: int) -> httpx.AsyncClient:
    """Cria um ``httpx.AsyncClient`` que limita a ``rpm`` requisições por minuto.

    Args:
        rpm: teto de requisições por minuto (>= 1).

    Returns:
        Cliente HTTP assíncrono com o limite embutido. Passe o MESMO cliente para
        todos os modelos (ex: via ``OpenRouterProvider(http_client=...)``) para que
        o teto seja compartilhado. O timeout é alto (600s) porque gerações de LLM
        podem demorar.
    """
    limiter = _Limiter(rpm)

    async def _hook(request: httpx.Request) -> None:  # noqa: ARG001 - assinatura do hook
        await limiter.aguardar()

    return httpx.AsyncClient(
        event_hooks={"request": [_hook]},
        timeout=httpx.Timeout(600.0),
    )
