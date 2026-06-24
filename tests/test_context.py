from loopforge.config import AppConfig
from loopforge.context import build_contexto

BASE = {
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
}


def test_funde_docs_da_cli_com_yaml():
    cfg = AppConfig.model_validate({**BASE, "contexto": {"docs": ["./d1"], "links": ["http://a"]}})
    ctx = build_contexto(cfg, extra_docs=["./d2"], extra_links=["http://b"])
    assert ctx.docs == ["./d1", "./d2"]
    assert ctx.links == ["http://a", "http://b"]
    assert ctx.best_practices_conteudo is None


def test_le_best_practices_quando_existe(tmp_path):
    bp = tmp_path / "SKILL.md"
    bp.write_text("regras asaas", encoding="utf-8")
    cfg = AppConfig.model_validate({**BASE, "skill": {"objetivo": "x", "best_practices": str(bp)}})
    ctx = build_contexto(cfg)
    assert ctx.best_practices_conteudo == "regras asaas"


def test_best_practices_arquivo_ausente(tmp_path):
    inexistente = tmp_path / "nao_existe" / "SKILL.md"
    cfg = AppConfig.model_validate({**BASE, "skill": {"objetivo": "x", "best_practices": str(inexistente)}})
    ctx = build_contexto(cfg)
    assert ctx.best_practices_conteudo is None
