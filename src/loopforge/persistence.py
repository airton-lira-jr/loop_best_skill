"""Gravação da skill gerada no diretório de saída + serde do checkpointer."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from pydantic import BaseModel

from loopforge import config as config_mod
from loopforge import state as state_mod
from loopforge.state import SkillArtifact


def _modelos_loopforge() -> list[type[BaseModel]]:
    """Lista os modelos Pydantic do loopforge que trafegam no checkpoint.

    O LangGraph serializa o estado do grafo via msgpack. Sem registrar nossos
    tipos, ele desserializa com WARNING ("unregistered type ... from checkpoint")
    e ameaça bloquear no futuro. Coletamos todos os ``BaseModel`` definidos em
    ``loopforge.state`` e ``loopforge.config`` para registrar de uma vez — fica
    correto mesmo quando novos modelos forem adicionados.

    Returns:
        Classes ``BaseModel`` definidas nesses dois módulos.
    """
    modelos: list[type[BaseModel]] = []
    for mod in (state_mod, config_mod):
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, BaseModel) and obj.__module__ == mod.__name__:
                modelos.append(obj)
    return modelos


def criar_serde():
    """Cria o serializer do checkpointer com nossos modelos na allowlist.

    Returns:
        ``JsonPlusSerializer`` que reconhece os tipos do loopforge, evitando os
        WARNINGs de "unregistered type" na desserialização do checkpoint.
    """
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(allowed_msgpack_modules=_modelos_loopforge())


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
