"""Testes do guardrail read-only das tools MCP (loopforge.mcp_readonly)."""

from __future__ import annotations

import pytest
from pydantic_ai.tools import ToolDefinition

from loopforge.mcp_readonly import eh_somente_leitura, filtro_readonly


def _td(nome: str, metadata: dict | None = None) -> ToolDefinition:
    """Monta um ToolDefinition mínimo p/ os testes."""
    return ToolDefinition(name=nome, parameters_json_schema={}, metadata=metadata)


@pytest.mark.parametrize(
    "nome",
    [
        # OpenMetadata (snake_case)
        "openmetadata_search_metadata",
        "get_entity_details",
        "get_entity_lineage",
        "search_metadata",
        # Atlassian (camelCase)
        "getJiraIssue",
        "searchJiraIssuesUsingJql",
        "getConfluencePage",
        "getConfluencePageFooterComments",
        "atlassianUserInfo",  # 'info' é termo de leitura
        # termos de leitura variados
        "list_files",
        "describe_table",
        "get_db_schema",
    ],
)
def test_libera_leitura(nome: str) -> None:
    assert eh_somente_leitura(_td(nome)) is True


@pytest.mark.parametrize(
    "nome",
    [
        # mutação de dados (snake_case)
        "patch_entity",
        "create_glossary",
        "create_glossary_term",
        "memory_save",
        "delete_label",
        "update_label",
        # mutação (camelCase, Atlassian)
        "createConfluencePage",
        "editJiraIssue",
        "updateConfluencePage",
        "addCommentToJiraIssue",
        "transitionJiraIssue",
        "createJiraIssue",
        # execução (altera estado) também bloqueia
        "smart_build",
        "run_impacted_tests",
        "execute_query",
        "corpus_build",
        # ambíguo (sem verbo conhecido) -> fail-closed
        "do_something_weird",
        "frobnicate",
    ],
)
def test_bloqueia_escrita_execucao_e_ambiguo(nome: str) -> None:
    assert eh_somente_leitura(_td(nome)) is False


def test_write_vence_read_no_mesmo_nome() -> None:
    # tem 'schema' (read) e 'update' (write): mutação tem prioridade.
    assert eh_somente_leitura(_td("update_schema")) is False


def test_hint_mutavel_bloqueia_nome_de_leitura() -> None:
    # nome parece leitura, mas o server declara readOnlyHint=False.
    assert eh_somente_leitura(_td("get_thing", {"readOnlyHint": False})) is False


def test_hint_readonly_libera_nome_ambiguo() -> None:
    # nome ambíguo, mas o server garante leitura via annotation.
    assert eh_somente_leitura(_td("frobnicate", {"readOnlyHint": True})) is True
    # também aceita aninhado em annotations
    assert eh_somente_leitura(_td("frobnicate", {"annotations": {"readOnlyHint": True}})) is True


def test_filtro_readonly_casa_assinatura_pydantic_ai() -> None:
    # filter_func(ctx, tool_def) -> bool; ctx é ignorado.
    assert filtro_readonly(None, _td("search_metadata")) is True
    assert filtro_readonly(None, _td("patch_entity")) is False
