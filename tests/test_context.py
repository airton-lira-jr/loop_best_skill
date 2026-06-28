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
    # fetcher no-op: não toca a rede no teste.
    ctx = build_contexto(cfg, extra_docs=["./d2"], extra_links=["http://b"], fetcher=lambda url: None)
    assert ctx.docs == ["./d1", "./d2"]
    assert ctx.links == ["http://a", "http://b"]
    assert ctx.best_practices_conteudo is None


def test_le_best_practices_quando_existe(tmp_path):
    bp = tmp_path / "SKILL.md"
    bp.write_text("regras de boas práticas", encoding="utf-8")
    cfg = AppConfig.model_validate({**BASE, "skill": {"objetivo": "x", "best_practices": str(bp)}})
    ctx = build_contexto(cfg, fetcher=lambda url: None)
    assert ctx.best_practices_conteudo == "regras de boas práticas"


def test_best_practices_arquivo_ausente(tmp_path):
    inexistente = tmp_path / "nao_existe" / "SKILL.md"
    cfg = AppConfig.model_validate({**BASE, "skill": {"objetivo": "x", "best_practices": str(inexistente)}})
    ctx = build_contexto(cfg, fetcher=lambda url: None)
    assert ctx.best_practices_conteudo is None


def test_le_conteudo_de_arquivo_e_diretorio_doc(tmp_path):
    arquivo = tmp_path / "a.md"
    arquivo.write_text("conteudo A", encoding="utf-8")
    pasta = tmp_path / "guia"
    pasta.mkdir()
    (pasta / "b.txt").write_text("conteudo B", encoding="utf-8")
    (pasta / "ignorar.bin").write_bytes(b"\x00\x01\x02")  # binário: ignorado

    cfg = AppConfig.model_validate(
        {**BASE, "contexto": {"docs": [str(arquivo), str(pasta)]}}
    )
    ctx = build_contexto(cfg, fetcher=lambda url: None)

    conteudos = {f.conteudo for f in ctx.docs_conteudo}
    assert "conteudo A" in conteudos
    assert "conteudo B" in conteudos
    assert not any("ignorar.bin" in f.origem for f in ctx.docs_conteudo)


def test_doc_path_inexistente_e_ignorado(tmp_path):
    cfg = AppConfig.model_validate(
        {**BASE, "contexto": {"docs": [str(tmp_path / "nada")]}}
    )
    ctx = build_contexto(cfg, fetcher=lambda url: None)
    assert ctx.docs_conteudo == []


def test_busca_conteudo_dos_links_com_fetcher():
    cfg = AppConfig.model_validate(
        {**BASE, "contexto": {"links": ["http://a", "http://b"]}}
    )
    ctx = build_contexto(cfg, fetcher=lambda url: f"corpo de {url}")
    assert {f.origem for f in ctx.links_conteudo} == {"http://a", "http://b"}
    assert any(f.conteudo == "corpo de http://a" for f in ctx.links_conteudo)


def test_link_que_falha_e_ignorado():
    cfg = AppConfig.model_validate(
        {**BASE, "contexto": {"links": ["http://ok", "http://falha"]}}
    )

    def fetch(url):
        return "ok" if url == "http://ok" else None

    ctx = build_contexto(cfg, fetcher=fetch)
    assert [f.origem for f in ctx.links_conteudo] == ["http://ok"]


def test_resolver_objetivo_texto_literal():
    from loopforge.context import resolver_objetivo

    assert resolver_objetivo("Skill que faz X") == "Skill que faz X"


def test_resolver_objetivo_le_arquivo(tmp_path):
    from loopforge.context import resolver_objetivo

    arq = tmp_path / "obj.md"
    arq.write_text("# Objetivo\nFazer X", encoding="utf-8")
    assert resolver_objetivo(str(arq)) == "# Objetivo\nFazer X"


def test_resolver_objetivo_concatena_diretorio(tmp_path):
    from loopforge.context import resolver_objetivo

    pasta = tmp_path / "objetivo"
    pasta.mkdir()
    (pasta / "a.md").write_text("parte A", encoding="utf-8")
    (pasta / "b.md").write_text("parte B", encoding="utf-8")
    out = resolver_objetivo(str(pasta))
    assert "parte A" in out and "parte B" in out
