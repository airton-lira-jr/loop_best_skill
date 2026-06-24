import textwrap
from types import SimpleNamespace

from typer.testing import CliRunner

import loopforge.cli as cli_mod
from loopforge.cli import app

runner = CliRunner()

CONFIG_BODY = """
    agents:
      discovery: {model: google-gla:gemini-2.0-flash}
      plan:      {model: anthropic:claude-opus-4-8}
      write:     {model: anthropic:claude-opus-4-8}
      judge:     {model: google-gla:gemini-2.0-flash}
    skill: {objetivo: "Skill de teste"}
"""


def _cfg(tmp_path, nome="config.yaml"):
    p = tmp_path / nome
    p.write_text(textwrap.dedent(CONFIG_BODY), encoding="utf-8")
    return p


def test_validate_ok(tmp_path):
    res = runner.invoke(app, ["validate", "--config", str(_cfg(tmp_path, "outro.yaml"))])
    assert res.exit_code == 0
    assert "válid" in res.stdout.lower()


def test_validate_arquivo_inexistente():
    res = runner.invoke(app, ["validate", "--config", "/nao/existe.yaml"])
    assert res.exit_code != 0


def test_validate_usa_config_yaml_por_padrao(tmp_path, monkeypatch):
    _cfg(tmp_path)  # cria ./config.yaml
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["validate"])  # sem --config
    assert res.exit_code == 0


def test_run_sem_subcomando_usa_config_yaml(monkeypatch):
    chamado = {}

    async def fake_run_loop(config_path, extra_docs=None, extra_links=None):
        chamado["config"] = config_path
        return SimpleNamespace(status="aprovado", score_final=0.9, iteracao=1)

    monkeypatch.setattr(cli_mod, "run_loop", fake_run_loop)
    res = runner.invoke(app, [])  # `loopforge` puro
    assert res.exit_code == 0
    assert chamado["config"] == "config.yaml"
