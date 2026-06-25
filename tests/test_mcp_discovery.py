import json
from pathlib import Path

from loopforge.config import AppConfig
from loopforge.mcp_discovery import descobrir_mcp_servers, materializar_mcp_config

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
    servers = descobrir_mcp_servers(cwd, home)
    assert set(servers) == {"glob", "proj", "local"}


def test_mcp_json_sobrescreve_global(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    _claude_json(home, {"mcpServers": {"x": {"command": "global"}}})
    (cwd / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"x": {"command": "local"}}}), encoding="utf-8"
    )
    servers = descobrir_mcp_servers(cwd, home)
    assert servers["x"]["command"] == "local"


def test_sem_fontes_retorna_vazio(tmp_path):
    assert descobrir_mcp_servers(tmp_path / "p", tmp_path / "h") == {}


def test_json_invalido_e_ignorado(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text("{nao eh json", encoding="utf-8")
    assert descobrir_mcp_servers(tmp_path / "p", home) == {}


def test_materializar_config_path_explicito_vence(tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"mcpServers": {}}', encoding="utf-8")
    cfg = AppConfig.model_validate({**BASE, "mcp": {"config_path": str(f)}})
    path, eh_temp = materializar_mcp_config(cfg)
    assert path == str(f)
    assert eh_temp is False


def test_materializar_auto_off_retorna_none(tmp_path):
    cfg = AppConfig.model_validate({**BASE, "mcp": {"auto": False}})
    path, eh_temp = materializar_mcp_config(cfg, cwd=tmp_path, home=tmp_path)
    assert path is None
    assert eh_temp is False


def test_materializar_auto_descobre_e_escreve_temp(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir(parents=True)
    _claude_json(home, {"mcpServers": {"glob": {"command": "g"}}})
    cfg = AppConfig.model_validate({**BASE, "mcp": {"auto": True}})
    path, eh_temp = materializar_mcp_config(cfg, cwd=cwd, home=home)
    try:
        assert eh_temp is True
        conteudo = json.loads(Path(path).read_text(encoding="utf-8"))
        assert "glob" in conteudo["mcpServers"]
    finally:
        Path(path).unlink(missing_ok=True)


def test_materializar_auto_sem_servers_retorna_none(tmp_path):
    cfg = AppConfig.model_validate({**BASE, "mcp": {"auto": True}})
    path, eh_temp = materializar_mcp_config(cfg, cwd=tmp_path / "p", home=tmp_path / "h")
    assert path is None
    assert eh_temp is False
