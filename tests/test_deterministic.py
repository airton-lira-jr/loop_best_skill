from loopforge.config import DeterministicoCfg
from loopforge.scoring.deterministic import score_deterministico
from loopforge.state import SkillArtifact, SkillFile

CFG = DeterministicoCfg()

SKILL_OK = (
    "---\n"
    "name: pr-review\n"
    "description: Use quando precisar revisar PRs de Python.\n"
    "---\n"
    "# PR Review\n\n"
    "Veja [refs](references/guia.md).\n"
)


def test_skill_perfeita_pontua_1():
    art = SkillArtifact(skill_md=SKILL_OK, arquivos=[SkillFile(caminho="references/guia.md", conteudo="x")])
    score, detalhes = score_deterministico(art, CFG)
    assert score == 1.0
    assert detalhes["frontmatter_valido"] == 1.0


def test_sem_trigger_perde_o_peso():
    skill = SKILL_OK.replace("Use quando precisar revisar PRs de Python.", "Revisor de PRs.")
    art = SkillArtifact(skill_md=skill, arquivos=[SkillFile(caminho="references/guia.md", conteudo="x")])
    score, detalhes = score_deterministico(art, CFG)
    assert detalhes["description_tem_trigger"] == 0.0
    assert score == 1.0 - CFG.description_tem_trigger


def test_budget_excedido_penaliza_proporcional():
    corpo = "\n".join(f"linha {i}" for i in range(620))
    skill = f"---\nname: x\ndescription: Use quando algo.\n---\n{corpo}\n"
    art = SkillArtifact(skill_md=skill)  # sem refs => refs_existem = 1.0
    score, detalhes = score_deterministico(art, DeterministicoCfg(budget_linhas=500))
    assert round(detalhes["dentro_budget"], 3) == round(max(0.0, 1 - (skill.count(chr(10)) + 1 - 500) / 500), 3)


def test_url_externa_nao_conta_como_ref():
    skill = (
        "---\n"
        "name: doc\n"
        "description: Use quando ler docs.\n"
        "---\n"
        "# Documentação\n\n"
        "Veja [docs](https://example.com/page.html).\n"
    )
    art = SkillArtifact(skill_md=skill, arquivos=[])
    score, detalhes = score_deterministico(art, CFG)
    assert detalhes["refs_existem"] == 1.0  # URL ignorada, sem penalidade


def test_refs_parciais():
    skill = (
        "---\n"
        "name: files\n"
        "description: Use quando processar.\n"
        "---\n"
        "# Processamento\n\n"
        "Veja [a](references/a.md) e [b](references/b.md).\n"
    )
    art = SkillArtifact(
        skill_md=skill,
        arquivos=[SkillFile(caminho="references/a.md", conteudo="")],
    )
    score, detalhes = score_deterministico(art, CFG)
    assert detalhes["refs_existem"] == 0.5  # 1 de 2 referências presentes


def test_sem_heading_markdown_invalido():
    skill = (
        "---\n"
        "name: x\n"
        "description: Use quando algo.\n"
        "---\n"
        "Sem heading, só texto.\n"
    )
    art = SkillArtifact(skill_md=skill, arquivos=[])
    score, detalhes = score_deterministico(art, CFG)
    assert detalhes["markdown_valido"] == 0.0  # sem # heading
