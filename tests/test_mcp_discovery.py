import json
from pathlib import Path

import pytest

from loopforge.config import AppConfig
from loopforge.mcp_discovery import (
    aplicar_filtros,
    descobrir_mcp_servers,
    preparar_mcp_config,
)

BASE = {
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
}


def _claude_json(home: Path, dados: dict):
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text(json.dumps(dados), encoding="utf-8")


# --- descoberta ---------------------------------------------------------------

def test_merge_global_projeto_e_mcp_json(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    _claude_json(home, {
        "mcpServers": {"glob": {"command": "g"}},
        "projects": {str(cwd): {"mcpServers": {"proj": {"command": "p"}}}},
    })
    (cwd / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"local": {"command": "l"}}}), encoding="utf-8"
    )
    assert set(descobrir_mcp_servers(cwd, home)) == {"glob", "proj", "local"}


def test_mcp_json_sobrescreve_global(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    _claude_json(home, {"mcpServers": {"x": {"command": "global"}}})
    (cwd / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"x": {"command": "local"}}}), encoding="utf-8"
    )
    assert descobrir_mcp_servers(cwd, home)["x"]["command"] == "local"


def test_sem_fontes_retorna_vazio(tmp_path):
    assert descobrir_mcp_servers(tmp_path / "p", tmp_path / "h") == {}


def test_json_invalido_e_ignorado(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text("{nao eh json", encoding="utf-8")
    assert descobrir_mcp_servers(tmp_path / "p", home) == {}


# --- filtros ------------------------------------------------------------------

def test_filtro_incluir_mantem_so_allowlist():
    servers = {"a": {}, "b": {}, "c": {}}
    assert set(aplicar_filtros(servers, ["a", "c"], [])) == {"a", "c"}


def test_filtro_excluir_remove_denylist():
    servers = {"a": {}, "b": {}, "c": {}}
    assert set(aplicar_filtros(servers, None, ["b"])) == {"a", "c"}


def test_filtro_none_mantem_tudo():
    servers = {"a": {}, "b": {}}
    assert set(aplicar_filtros(servers, None, [])) == {"a", "b"}


# --- preparar (com probe injetado) -------------------------------------------

def _cfg(mcp: dict):
    return AppConfig.model_validate({**BASE, "mcp": mcp})


@pytest.mark.anyio
async def test_preparar_config_path_explicito_vence(tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"mcpServers": {}}', encoding="utf-8")
    path, eh_temp = await preparar_mcp_config(_cfg({"config_path": str(f)}))
    assert path == str(f)
    assert eh_temp is False


@pytest.mark.anyio
async def test_preparar_auto_off_retorna_none(tmp_path):
    path, eh_temp = await preparar_mcp_config(
        _cfg({"auto": False}), cwd=tmp_path, home=tmp_path
    )
    assert path is None
    assert eh_temp is False


@pytest.mark.anyio
async def test_preparar_descarta_servers_que_falham_no_probe(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    _claude_json(home, {"mcpServers": {"bom": {"command": "ok"}, "ruim": {"command": "x"}}})

    async def prober(nome, defn):
        return nome == "bom"  # só "bom" é saudável

    path, eh_temp = await preparar_mcp_config(
        _cfg({"auto": True}), cwd=cwd, home=home, prober=prober
    )
    try:
        assert eh_temp is True
        conteudo = json.loads(Path(path).read_text(encoding="utf-8"))
        assert set(conteudo["mcpServers"]) == {"bom"}
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.anyio
async def test_preparar_todos_falham_retorna_none(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    _claude_json(home, {"mcpServers": {"a": {"command": "x"}}})

    async def prober(nome, defn):
        return False

    path, eh_temp = await preparar_mcp_config(
        _cfg({"auto": True}), cwd=cwd, home=home, prober=prober
    )
    assert path is None
    assert eh_temp is False


@pytest.mark.anyio
async def test_preparar_respeita_excluir(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    _claude_json(home, {"mcpServers": {"a": {"command": "x"}, "b": {"command": "y"}}})
    sondados = []

    async def prober(nome, defn):
        sondados.append(nome)
        return True

    path, eh_temp = await preparar_mcp_config(
        _cfg({"auto": True, "excluir": ["a"]}), cwd=cwd, home=home, prober=prober
    )
    try:
        assert sondados == ["b"]  # "a" filtrado antes do probe
        conteudo = json.loads(Path(path).read_text(encoding="utf-8"))
        assert set(conteudo["mcpServers"]) == {"b"}
    finally:
        Path(path).unlink(missing_ok=True)
