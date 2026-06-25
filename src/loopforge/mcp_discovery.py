"""Auto-descoberta dos servidores MCP da sessão do Claude Code.

O loopforge reaproveita os servers MCP **locais** que o Claude Code já tem
configurados, sem exigir nada no YAML. As fontes (mescladas nesta ordem, a
última vence em caso de nome repetido) são:

1. ``~/.claude.json`` -> ``mcpServers`` (escopo global do usuário)
2. ``~/.claude.json`` -> ``projects[<cwd>].mcpServers`` (escopo do projeto)
3. ``<cwd>/.mcp.json`` -> ``mcpServers`` (arquivo do projeto)

Limitação: connectors hospedados no claude.ai (OAuth da sessão) NÃO aparecem
nesses arquivos e, portanto, não podem ser herdados por um processo separado.
Só servers locais (stdio/sse/http definidos nesses JSONs) são reaproveitados.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loopforge.config import AppConfig
from loopforge.logging import get_logger

log = get_logger("mcp_discovery")


def _ler_json(caminho: Path) -> dict[str, Any]:
    """Lê um JSON; devolve {} se ausente ou inválido."""
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def descobrir_mcp_servers(cwd: Path, home: Path) -> dict[str, Any]:
    """Mescla os ``mcpServers`` das fontes do Claude Code.

    Args:
        cwd: diretório do projeto (onde rodaria o loopforge).
        home: diretório home do usuário (onde fica ``~/.claude.json``).

    Returns:
        Dicionário ``{nome_do_server: definição}`` mesclado (pode ser vazio).
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


def materializar_mcp_config(
    config: AppConfig,
    cwd: Path | None = None,
    home: Path | None = None,
) -> tuple[str | None, bool]:
    """Resolve o caminho do JSON de MCP a ser usado pelo build dos agentes.

    Precedência:
    1. ``mcp.config_path`` explícito -> usa esse arquivo (sem auto-descoberta).
    2. ``mcp.auto`` False -> sem MCP.
    3. auto-descoberta: mescla as fontes do Claude Code e, se houver servers,
       grava um arquivo temporário (0600) com ``{"mcpServers": ...}``.

    Args:
        config: configuração carregada.
        cwd: diretório do projeto (default: diretório atual).
        home: home do usuário (default: home real).

    Returns:
        ``(caminho_ou_None, eh_temporario)``. Quando ``eh_temporario`` é True, o
        chamador deve apagar o arquivo após construir as toolsets.
    """
    if config.mcp.config_path:
        return config.mcp.config_path, False
    if not config.mcp.auto:
        return None, False

    cwd = cwd or Path.cwd()
    home = home or Path.home()
    servers = descobrir_mcp_servers(cwd, home)
    if not servers:
        return None, False

    fd, tmp = tempfile.mkstemp(prefix="loopforge-mcp-", suffix=".json")
    try:
        os.write(fd, json.dumps({"mcpServers": servers}).encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    log.info("mcp_auto_descoberto", servers=sorted(servers), arquivo_temp=tmp)
    return tmp, True
