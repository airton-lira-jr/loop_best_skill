"""Camada determinística do score: checks programáticos sobre a skill."""

from __future__ import annotations

import re

import yaml

from loopforge.config import DeterministicoCfg
from loopforge.state import SkillArtifact

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TRIGGER = re.compile(r"use\s+(when|quando)", re.IGNORECASE)
_REF_LINK = re.compile(r"\]\(([^)]+\.\w+)\)")


def _parse_frontmatter(skill_md: str) -> dict | None:
    """Extrai e parseia o frontmatter YAML; None se ausente/inválido."""
    m = _FRONTMATTER.match(skill_md)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


def score_deterministico(
    artifact: SkillArtifact, cfg: DeterministicoCfg
) -> tuple[float, dict[str, float]]:
    """Pontua a skill com checks determinísticos.

    Args:
        artifact: skill escrita.
        cfg: pesos e budget de linhas.

    Returns:
        (score 0..1, dict com a contribuição 0..1 de cada check antes do peso).
    """
    fm = _parse_frontmatter(artifact.skill_md)
    detalhes: dict[str, float] = {}

    detalhes["frontmatter_valido"] = 1.0 if fm and "name" in fm and "description" in fm else 0.0

    descricao = str(fm.get("description", "")) if fm else ""
    detalhes["description_tem_trigger"] = 1.0 if _TRIGGER.search(descricao) else 0.0

    linhas = artifact.skill_md.count("\n") + 1
    if linhas <= cfg.budget_linhas:
        detalhes["dentro_budget"] = 1.0
    else:
        detalhes["dentro_budget"] = max(0.0, 1 - (linhas - cfg.budget_linhas) / cfg.budget_linhas)

    referenciados = set(_REF_LINK.findall(artifact.skill_md))
    # Filtrar URLs externas (começam com http:// ou https://)
    referenciados = {r for r in referenciados if not r.startswith(("http://", "https://"))}
    if not referenciados:
        detalhes["refs_existem"] = 1.0
    else:
        presentes = {f.caminho for f in artifact.arquivos}
        existentes = sum(1 for r in referenciados if r in presentes)
        detalhes["refs_existem"] = existentes / len(referenciados)

    tem_heading = bool(re.search(r"^#\s", artifact.skill_md, re.MULTILINE))
    detalhes["markdown_valido"] = 1.0 if (fm is not None and tem_heading) else 0.0

    score = (
        cfg.frontmatter_valido * detalhes["frontmatter_valido"]
        + cfg.description_tem_trigger * detalhes["description_tem_trigger"]
        + cfg.dentro_budget * detalhes["dentro_budget"]
        + cfg.refs_existem * detalhes["refs_existem"]
        + cfg.markdown_valido * detalhes["markdown_valido"]
    )
    return score, detalhes
