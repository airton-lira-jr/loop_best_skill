from loopforge.persistence import gravar_skill
from loopforge.state import SkillArtifact, SkillFile


def test_grava_skill_md_e_refs(tmp_path):
    art = SkillArtifact(
        skill_md="---\nname: x\ndescription: Use quando.\n---\n# X\n",
        arquivos=[SkillFile(caminho="references/guia.md", conteudo="conteudo")],
    )
    destino = gravar_skill(art, tmp_path, "minha-skill")
    assert (destino / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert (destino / "references" / "guia.md").read_text(encoding="utf-8") == "conteudo"
