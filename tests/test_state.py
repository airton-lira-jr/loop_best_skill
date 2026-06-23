from loopforge.state import (
    DimensaoNota, JudgeVerdict, SkillArtifact, SkillFile, SkillPlan,
)


def test_skill_artifact_aceita_arquivos():
    art = SkillArtifact(
        skill_md="---\nname: x\ndescription: Use quando...\n---\n# X\n",
        arquivos=[SkillFile(caminho="references/a.md", conteudo="...")],
    )
    assert art.arquivos[0].caminho == "references/a.md"


def test_judge_verdict_dimensoes_tipadas():
    v = JudgeVerdict(
        alinhamento_objetivo=DimensaoNota(nota=0.9, rationale="ok"),
        discoverability=DimensaoNota(nota=0.8, rationale="ok"),
        concisao_clareza=DimensaoNota(nota=0.7, rationale="ok"),
        completude=DimensaoNota(nota=0.85, rationale="ok"),
        aderencia_best_practices=DimensaoNota(nota=0.9, rationale="ok"),
        feedback_acionavel="melhore a description",
    )
    assert 0.0 <= v.discoverability.nota <= 1.0
