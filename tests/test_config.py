import textwrap
import pytest
from pydantic import ValidationError
from loopforge.config import load_config


def _write(tmp_path, body: str):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_load_config_minimo_aplica_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, """
        agents:
          discovery: {model: google-gla:gemini-2.0-flash}
          plan:      {model: anthropic:claude-opus-4-8}
          write:     {model: anthropic:claude-opus-4-8}
          judge:     {model: google-gla:gemini-2.0-flash}
        skill:
          objetivo: "Gerar uma skill de review de PR"
    """))
    assert cfg.skill.output_dir == "./skills"
    assert cfg.loop.max_iteracoes == 6
    assert cfg.loop.score_minimo == 0.8
    assert cfg.scoring.pesos.deterministico == 0.30
    assert cfg.scoring.deterministico.budget_linhas == 500


def test_pesos_que_nao_somam_um_falham(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, """
            agents:
              discovery: {model: google-gla:gemini-2.0-flash}
              plan:      {model: anthropic:claude-opus-4-8}
              write:     {model: anthropic:claude-opus-4-8}
              judge:     {model: google-gla:gemini-2.0-flash}
            skill: {objetivo: "x"}
            scoring:
              pesos: {deterministico: 0.5, judge: 0.9}
        """))


def test_deterministico_que_nao_soma_um_falha(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, """
            agents:
              discovery: {model: google-gla:gemini-2.0-flash}
              plan:      {model: anthropic:claude-opus-4-8}
              write:     {model: anthropic:claude-opus-4-8}
              judge:     {model: google-gla:gemini-2.0-flash}
            skill:
              objetivo: "Gerar uma skill de review de PR"
            scoring:
              deterministico: {frontmatter_valido: 0.9}
        """))


def test_judge_que_nao_soma_um_falha(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, """
            agents:
              discovery: {model: google-gla:gemini-2.0-flash}
              plan:      {model: anthropic:claude-opus-4-8}
              write:     {model: anthropic:claude-opus-4-8}
              judge:     {model: google-gla:gemini-2.0-flash}
            skill:
              objetivo: "Gerar uma skill de review de PR"
            scoring:
              judge: {alinhamento_objetivo: 0.9}
        """))


def test_mcp_defaults_e_best_practices_opcional(tmp_path):
    cfg = load_config(_write(tmp_path, """
        agents:
          discovery: {model: google-gla:gemini-2.0-flash}
          plan:      {model: anthropic:claude-opus-4-8}
          write:     {model: anthropic:claude-opus-4-8}
          judge:     {model: google-gla:gemini-2.0-flash}
        skill: {objetivo: "x"}
    """))
    assert cfg.skill.best_practices is None          # best_practices é opcional
    assert cfg.mcp.config_path is None               # sem MCP por default
    assert cfg.mcp.agentes == ["discovery", "plan", "write"]


def test_mcp_agente_invalido_falha(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, """
            agents:
              discovery: {model: google-gla:gemini-2.0-flash}
              plan:      {model: anthropic:claude-opus-4-8}
              write:     {model: anthropic:claude-opus-4-8}
              judge:     {model: google-gla:gemini-2.0-flash}
            skill: {objetivo: "x"}
            mcp: {config_path: "./m.json", agentes: ["discovery", "xpto"]}
        """))
