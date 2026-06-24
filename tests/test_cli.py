import textwrap

from typer.testing import CliRunner

from loopforge.cli import app

runner = CliRunner()


def _cfg(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent("""
        agents:
          discovery: {model: google-gla:gemini-2.0-flash}
          plan:      {model: anthropic:claude-opus-4-8}
          write:     {model: anthropic:claude-opus-4-8}
          judge:     {model: google-gla:gemini-2.0-flash}
        skill: {objetivo: "Skill de teste"}
    """), encoding="utf-8")
    return p


def test_validate_ok(tmp_path):
    res = runner.invoke(app, ["validate", "--config", str(_cfg(tmp_path))])
    assert res.exit_code == 0
    assert "válid" in res.stdout.lower()


def test_validate_arquivo_inexistente():
    res = runner.invoke(app, ["validate", "--config", "/nao/existe.yaml"])
    assert res.exit_code != 0
