import logging

from loopforge.config import AppConfig
from loopforge.persistence import (
    _modelos_loopforge,
    criar_serde,
    gravar_run_md,
    gravar_skill,
)
from loopforge.state import (
    Abordagem,
    Contexto,
    DiscoveryReport,
    LoopState,
    SkillArtifact,
    SkillFile,
    SkillPlan,
)


def test_serde_registra_modelos_loopforge():
    """A allowlist do serde cobre os modelos que trafegam no checkpoint."""
    nomes = {m.__name__ for m in _modelos_loopforge()}
    assert {"Contexto", "AppConfig", "DiscoveryReport", "LoopState"} <= nomes


def test_serde_round_trip_sem_warning(caplog):
    """Round-trip de um modelo registrado não emite WARNING de 'unregistered type'."""
    serde = criar_serde()
    with caplog.at_level(logging.WARNING, logger="langgraph.checkpoint.serde.jsonplus"):
        tipo, blob = serde.dumps_typed(Contexto(docs=["a"]))
        out = serde.loads_typed((tipo, blob))
    assert isinstance(out, Contexto)
    assert not any("unregistered" in r.getMessage() for r in caplog.records)


def test_grava_skill_md_e_refs(tmp_path):
    art = SkillArtifact(
        skill_md="---\nname: x\ndescription: Use quando.\n---\n# X\n",
        arquivos=[SkillFile(caminho="references/guia.md", conteudo="conteudo")],
    )
    destino = gravar_skill(art, tmp_path, "minha-skill")
    assert (destino / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert (destino / "references" / "guia.md").read_text(encoding="utf-8") == "conteudo"


def test_grava_skill_sanitiza_caminhos_inseguros(tmp_path):
    """URL/caminho absoluto/traversal não escapam do diretório da skill (fail-closed)."""
    art = SkillArtifact(
        skill_md="---\nname: x\ndescription: Use quando.\n---\n# X\n",
        arquivos=[
            SkillFile(caminho="https://asaas.example/wiki/AIE04+Design", conteudo="url"),
            SkillFile(caminho="/etc/evil", conteudo="abs"),
            SkillFile(caminho="../../fora", conteudo="trav"),
            SkillFile(caminho="reference/ok.md", conteudo="ok"),
        ],
    )
    destino = gravar_skill(art, tmp_path, "s")
    # traversal foi rejeitado: nada escreveu fora do destino
    assert not (tmp_path / "fora").exists()
    assert not (tmp_path.parent / "fora").exists()
    # URL virou só o nome final, dentro do destino (sem árvore de diretórios da URL)
    assert (destino / "AIE04+Design").read_text(encoding="utf-8") == "url"
    assert not (destino / "https:").exists()
    # caminho absoluto vira relativo dentro do destino
    assert (destino / "etc" / "evil").read_text(encoding="utf-8") == "abs"
    # caminho relativo válido segue funcionando
    assert (destino / "reference" / "ok.md").read_text(encoding="utf-8") == "ok"


def test_grava_run_md_documenta_a_trilha(tmp_path):
    """RUN.md materializa o que cada agente pesquisou/decidiu/escreveu."""
    cfg = AppConfig.model_validate(
        {
            "agents": {
                "discovery": {"model": "nvidia:meta/llama-3.3-70b-instruct"},
                "plan": {"model": "nvidia:meta/llama-3.3-70b-instruct"},
                "write": {"model": "nvidia:meta/llama-3.3-70b-instruct"},
                "judge": {"model": "nvidia:meta/llama-3.1-70b-instruct"},
            },
            "skill": {"objetivo": "x"},
            "websearch": {"habilitado": False},
        }
    )
    state = LoopState(
        objetivo="construir agente Slack",
        contexto=Contexto(),
        config=cfg,
        discovery_report=DiscoveryReport(
            achados=["RAG melhora precisão"],
            fontes=["https://docs.exemplo"],
            abordagens=[Abordagem(nome="RAG", resumo="r", adequacao=0.9)],
            recomendada="RAG",
            justificativa="j",
        ),
        plan=SkillPlan(
            name="agente-slack",
            description="Use quando integrar IA ao Slack",
            estrutura="e",
            secoes=["Overview", "Quando usar"],
            notas_para_write="citar a fonte X",
            justificativa="j",
        ),
        artifact=SkillArtifact(skill_md="---\n...", notas_de_escrita="optei por progressive disclosure"),
        status="aprovado",
    )
    destino = tmp_path / "agente-slack"
    destino.mkdir()
    caminho = gravar_run_md(state, destino)
    txt = caminho.read_text(encoding="utf-8")
    assert caminho.name == "RUN.md"
    for esperado in (
        "construir agente Slack",
        "RAG melhora precisão",
        "citar a fonte X",
        "optei por progressive disclosure",
        "## Discovery",
        "## Plan",
    ):
        assert esperado in txt
