import logging

from loopforge.persistence import _modelos_loopforge, criar_serde, gravar_skill
from loopforge.state import Contexto, SkillArtifact, SkillFile


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
