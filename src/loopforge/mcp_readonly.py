"""Guardrail read-only para as tools MCP entregues aos agentes.

Regra de produto (invariante): esta aplicação **só consulta** serviços externos
(Jira, Confluence, OpenMetadata e quaisquer outros) via MCP — **nunca** cria,
edita ou apaga nada neles. A única escrita permitida é a própria SKILL gerada,
gravada localmente pelo runner (``gravar_skill``), nunca por uma tool MCP.

Para garantir isso, toda toolset MCP passa por um filtro **fail-closed** antes de
chegar ao agente: só tools claramente de leitura sobrevivem. Critério de decisão
para cada tool (nesta ordem):

1. Se a tool traz a annotation MCP ``readOnlyHint=False`` (ela mesma se declara
   mutável) -> **bloqueia**.
2. Se o nome contém um verbo de mutação (create/update/delete/...) -> **bloqueia**.
3. Se o nome contém um verbo/termo de leitura (get/list/search/...) -> **libera**.
4. Caso ambíguo (não bater em nada) -> **bloqueia** (fail-closed).

O nome é tokenizado tanto em ``snake_case`` quanto em ``camelCase``, cobrindo os
dois estilos comuns (``patch_entity`` do OpenMetadata, ``createConfluencePage``
do Atlassian). O prefixo do server (``openmetadata_*``) não atrapalha: ele vira
só mais um token, ignorado por não ser verbo.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic_ai.tools import ToolDefinition

# Verbos de mutação. Qualquer um presente no nome => a tool escreve/altera/executa
# e é bloqueada. Inclui mutação de dados (create/update/delete) e execução
# (run/exec/trigger) — execução também pode alterar estado, então não passa.
WRITE_VERBS: frozenset[str] = frozenset(
    {
        "create", "update", "delete", "edit", "patch", "add", "remove", "insert",
        "replace", "move", "write", "set", "put", "post", "save", "store",
        "archive", "transition", "complete", "send", "schedule", "draft",
        "upload", "copy", "label", "unlabel", "merge", "purge", "clear",
        "invalidate", "warmup", "reindex", "init", "rename", "comment", "react",
        "link", "unlink", "sync", "apply", "run", "exec", "execute", "trigger",
        "restart", "stop", "kill", "drop", "build", "compress", "decompress",
        "optimize", "partition", "replicate", "migrate", "switch", "register",
        "enable", "disable", "grant", "revoke", "assign", "close", "open",
        "start", "cancel", "import", "export", "checkpoint",
    }
)

# Verbos/termos de leitura. Liberam a tool SE nenhum verbo de mutação estiver
# presente (a checagem de mutação tem prioridade, então `update_schema` bloqueia
# mesmo tendo `schema`).
READ_VERBS: frozenset[str] = frozenset(
    {
        "get", "list", "search", "read", "fetch", "find", "query", "describe",
        "show", "lookup", "count", "view", "status", "stats", "summary",
        "summarize", "analyze", "discover", "inspect", "detect", "diff",
        "explain", "schema", "dependencies", "dependents", "callers", "callees",
        "impact", "context", "history", "preview", "check", "report", "trace",
        "info", "metadata", "lineage", "structure", "routes", "classes",
        "functions", "imports",
    }
)

_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_SEP = re.compile(r"[^a-zA-Z0-9]+")


def _tokens(nome: str) -> set[str]:
    """Quebra um nome de tool em tokens, cobrindo snake_case e camelCase.

    ``getJiraIssue`` -> {get, jira, issue}; ``patch_entity`` -> {patch, entity}.
    """
    com_espaco = _CAMEL.sub(r"\1 \2", nome)
    return {t for t in _SEP.split(com_espaco.lower()) if t}


def _readonly_hint(metadata: Any) -> bool | None:
    """Extrai a annotation MCP ``readOnlyHint`` do metadata, se houver.

    Returns:
        True/False se a tool declarou o hint; None se ausente/indisponível.
    """
    if not isinstance(metadata, dict):
        return None
    if "readOnlyHint" in metadata:
        return bool(metadata["readOnlyHint"])
    anota = metadata.get("annotations")
    if isinstance(anota, dict) and "readOnlyHint" in anota:
        return bool(anota["readOnlyHint"])
    return None


def eh_somente_leitura(tool_def: ToolDefinition) -> bool:
    """Decide se uma tool MCP é de leitura pura (fail-closed).

    Args:
        tool_def: definição da tool (nome + metadata) vista pelo agente.

    Returns:
        True se a tool pode ser exposta ao agente (só consulta); False se deve
        ser bloqueada (escreve, executa ou é ambígua).
    """
    hint = _readonly_hint(tool_def.metadata)
    if hint is False:
        return False  # a própria tool se declara mutável

    toks = _tokens(tool_def.name)
    if toks & WRITE_VERBS:
        return False
    if toks & READ_VERBS:
        return True
    if hint is True:
        return True  # nome ambíguo, mas o server garante read-only
    return False  # fail-closed: na dúvida, bloqueia


def filtro_readonly(_ctx: Any, tool_def: ToolDefinition) -> bool:
    """Predicate p/ ``AbstractToolset.filtered`` — só deixa passar tool de leitura.

    Assinatura casa com ``filter_func(ctx, tool_def) -> bool`` do PydanticAI.
    """
    return eh_somente_leitura(tool_def)
