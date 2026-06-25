"""Auto-descoberta e preparação resiliente dos servidores MCP da sessão.

O loopforge reaproveita os servers MCP **locais** que o Claude Code já tem
configurados, sem exigir nada no YAML. Fontes (mescladas nesta ordem, a última
vence em nome repetido):

1. ``~/.claude.json`` -> ``mcpServers`` (escopo global do usuário)
2. ``~/.claude.json`` -> ``projects[<cwd>].mcpServers`` (escopo do projeto)
3. ``<cwd>/.mcp.json`` -> ``mcpServers`` (arquivo do projeto)

Depois aplica os filtros ``mcp.incluir``/``mcp.excluir`` e faz um *probe*: cada
server é conectado isoladamente e os que falharem são DESCARTADOS (um server
quebrado nunca derruba o loop).

Limitação: connectors hospedados no claude.ai (OAuth da sessão) NÃO aparecem
nesses arquivos e não podem ser herdados por um processo separado.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic_ai.mcp import load_mcp_toolsets

from loopforge.config import AppConfig
from loopforge.logging import get_logger

log = get_logger("mcp_discovery")

# Probe de um server: (nome, definição) -> saudável? (injetável em teste).
Prober = Callable[[str, dict[str, Any]], Awaitable[bool]]

_PROBE_TIMEOUT = 20.0


def _ler_json(caminho: Path) -> dict[str, Any]:
    """Lê um JSON; devolve {} se ausente ou inválido."""
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def descobrir_mcp_servers(cwd: Path, home: Path) -> dict[str, Any]:
    """Mescla os ``mcpServers`` das fontes do Claude Code.

    Args:
        cwd: diretório do projeto.
        home: home do usuário (onde fica ``~/.claude.json``).

    Returns:
        Dicionário ``{nome: definição}`` mesclado (pode ser vazio).
    """
    servers: dict[str, Any] = {}

    claude_json = _ler_json(home / ".claude.json")
    if isinstance(claude_json.get("mcpServers"), dict):
        servers.update(claude_json["mcpServers"])
    projeto = (claude_json.get("projects") or {}).get(str(cwd)) or {}
    if isinstance(projeto.get("mcpServers"), dict):
        servers.update(projeto["mcpServers"])

    mcp_json = _ler_json(cwd / ".mcp.json")
    if isinstance(mcp_json.get("mcpServers"), dict):
        servers.update(mcp_json["mcpServers"])

    return servers


def aplicar_filtros(
    servers: dict[str, Any],
    incluir: list[str] | None,
    excluir: list[str],
) -> dict[str, Any]:
    """Filtra servers por allowlist (``incluir``) e denylist (``excluir``).

    Args:
        servers: mapa de servers descobertos.
        incluir: se não-None, mantém só esses nomes.
        excluir: remove esses nomes.

    Returns:
        Subconjunto filtrado de ``servers``.
    """
    excluir_set = set(excluir)
    return {
        nome: defn
        for nome, defn in servers.items()
        if (incluir is None or nome in incluir) and nome not in excluir_set
    }


async def _probe_real(nome: str, defn: dict[str, Any]) -> bool:
    """Tenta conectar a um server MCP isolado; True se subiu, False se falhou.

    Escreve um JSON temporário com só esse server, carrega a toolset e faz
    enter/exit com timeout. Qualquer erro (binário ausente, init falho, timeout)
    é tratado como server não-saudável.

    Args:
        nome: nome do server.
        defn: definição (command/args/env/...).

    Returns:
        True se o server conectou e inicializou; False caso contrário.
    """
    fd, tmp = tempfile.mkstemp(prefix="loopforge-mcp-probe-", suffix=".json")
    try:
        os.write(fd, json.dumps({"mcpServers": {nome: defn}}).encode("utf-8"))
    finally:
        os.close(fd)
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT):
            for toolset in load_mcp_toolsets(tmp):
                async with toolset:
                    pass
        return True
    except Exception as exc:  # noqa: BLE001 - server ruim não pode derrubar o loop
        log.warning("mcp_server_ignorado", server=nome, erro=str(exc)[:200])
        return False
    finally:
        Path(tmp).unlink(missing_ok=True)


async def preparar_mcp_config(
    config: AppConfig,
    cwd: Path | None = None,
    home: Path | None = None,
    prober: Prober | None = None,
) -> tuple[str | None, bool]:
    """Resolve o JSON de MCP efetivo (com filtros + probe) para os agentes.

    Precedência:
    1. ``mcp.config_path`` explícito -> usa o arquivo como está (sem probe).
    2. ``mcp.auto`` False -> sem MCP.
    3. auto: descobre os servers, aplica ``incluir``/``excluir``, descarta os que
       falham no probe e grava um JSON temporário (0600) com os saudáveis.

    Args:
        config: configuração carregada.
        cwd: diretório do projeto (default: atual).
        home: home do usuário (default: real).
        prober: função de probe (injetável em teste; default conecta de verdade).

    Returns:
        ``(caminho_ou_None, eh_temporario)``. Se ``eh_temporario``, o chamador
        deve apagar o arquivo após construir as toolsets.
    """
    if config.mcp.config_path:
        return config.mcp.config_path, False
    if not config.mcp.auto:
        return None, False

    cwd = cwd or Path.cwd()
    home = home or Path.home()
    servers = aplicar_filtros(
        descobrir_mcp_servers(cwd, home), config.mcp.incluir, config.mcp.excluir
    )
    if not servers:
        return None, False

    probe = prober or _probe_real
    nomes = list(servers)
    resultados = await asyncio.gather(*(probe(n, servers[n]) for n in nomes))
    saudaveis = {n: servers[n] for n, ok in zip(nomes, resultados) if ok}
    if not saudaveis:
        log.warning("mcp_nenhum_server_saudavel", descobertos=sorted(servers))
        return None, False

    fd, tmp = tempfile.mkstemp(prefix="loopforge-mcp-", suffix=".json")
    try:
        os.write(fd, json.dumps({"mcpServers": saudaveis}).encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    log.info("mcp_pronto", servers=sorted(saudaveis), arquivo_temp=tmp)
    return tmp, True
