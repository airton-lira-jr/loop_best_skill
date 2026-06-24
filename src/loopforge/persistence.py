"""Gravação da skill gerada no diretório de saída."""

from __future__ import annotations

import re
from pathlib import Path

from loopforge.state import SkillArtifact


def _slug(nome: str) -> str:
    """Normaliza um nome para diretório (minúsculo, hífens).

    Args:
        nome: nome lógico da skill.

    Returns:
        Slug seguro para nome de diretório.
    """
    s = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")
    return s or "skill"


def gravar_skill(artifact: SkillArtifact, output_dir: str | Path, nome: str) -> Path:
    """Grava SKILL.md e arquivos referenciados em <output_dir>/<slug(nome)>/.

    Args:
        artifact: skill a gravar.
        output_dir: diretório raiz de saída.
        nome: nome lógico da skill (vira o subdiretório, em slug).

    Returns:
        Caminho do diretório da skill gravada.
    """
    destino = Path(output_dir) / _slug(nome)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "SKILL.md").write_text(artifact.skill_md, encoding="utf-8")

    for arq in artifact.arquivos:
        caminho = destino / arq.caminho
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(arq.conteudo, encoding="utf-8")
    return destino
