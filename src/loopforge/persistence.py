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


def _arquivo_destino(destino: Path, caminho: str) -> Path | None:
    """Resolve um caminho de arquivo referenciado para DENTRO de ``destino``.

    Sanitiza a entrada do LLM (que às vezes vem como URL, caminho absoluto ou com
    ``..``): URL vira só o nome final, ``/`` inicial é removido e qualquer
    resultado que escape do diretório da skill é rejeitado. É a única barreira
    entre o output do modelo e o sistema de arquivos, então é fail-closed.

    Args:
        destino: diretório da skill (raiz permitida).
        caminho: caminho relativo proposto pelo agente Write.

    Returns:
        ``Path`` seguro dentro de ``destino``, ou ``None`` se inseguro/vazio.
    """
    bruto = caminho.strip()
    if "://" in bruto:  # LLM passou uma URL como caminho — usa só o nome final
        bruto = bruto.rsplit("/", 1)[-1]
    bruto = bruto.lstrip("/")
    if not bruto:
        return None
    raiz = destino.resolve()
    alvo = (raiz / bruto).resolve()
    if alvo == raiz or raiz not in alvo.parents:  # traversal para fora da skill
        return None
    return alvo


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
        caminho = _arquivo_destino(destino, arq.caminho)
        if caminho is None:  # caminho inseguro (URL/absoluto/traversal) — pula
            continue
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(arq.conteudo, encoding="utf-8")
    return destino


def _bullets(itens: list[str]) -> str:
    """Renderiza uma lista como bullets markdown (ou '—' se vazia)."""
    return "\n".join(f"- {x}" for x in itens) or "—"


def gravar_run_md(state: "state_mod.LoopState", destino: Path) -> Path:
    """Grava um ``RUN.md`` com a trilha de raciocínio do loop ao lado da skill.

    Materializa em disco o que cada agente pesquisou/decidiu/escreveu (Discovery,
    Plan, Write, Judge) + o histórico de scores. É a versão inspecionável e
    auditável da trilha que trafega no estado do grafo — cumpre a regra de que cada
    agente documenta seu trabalho para os seguintes.

    Args:
        state: estado final do loop (com discovery_report/plan/artifact/verdict).
        destino: diretório da skill (onde o ``SKILL.md`` foi gravado).

    Returns:
        Caminho do ``RUN.md`` gravado.
    """
    p: list[str] = ["# RUN.md — trilha do LoopForge", ""]
    p += [
        f"- **Status:** {state.status}",
        f"- **Iterações:** {state.iteracao}",
        f"- **Score final:** {state.score_final:.4f} "
        f"(determinístico {state.score_det:.4f} / judge {state.score_judge:.4f})",
        "",
        "## Objetivo",
        state.objetivo,
        "",
    ]

    d = state.discovery_report
    p += ["## Discovery (pesquisa)"]
    if d is None:
        p += ["—", ""]
    else:
        abordagens = "\n".join(
            f"- **{a.nome}** (adequação {a.adequacao:.2f}): {a.resumo}" for a in d.abordagens
        ) or "—"
        p += [
            "**Achados:**", _bullets(d.achados),
            "", f"**Fontes:** {', '.join(d.fontes) or '—'}",
            "", "**Abordagens:**", abordagens,
            "", f"**Recomendada:** {d.recomendada} — {d.justificativa}", "",
        ]

    pl = state.plan
    p += ["## Plan (spec)"]
    if pl is None:
        p += ["—", ""]
    else:
        p += [
            f"- **name:** {pl.name}",
            f"- **description:** {pl.description}",
            f"- **estrutura:** {pl.estrutura}",
            f"- **seções:** {', '.join(pl.secoes) or '—'}",
            f"- **arquivos:** {', '.join(pl.arquivos) or '—'}",
            "", "**Notas para o Write:**", pl.notas_para_write or "—",
            "", "**Justificativa:**", pl.justificativa, "",
        ]

    art = state.artifact
    p += ["## Write (notas de escrita)", (art.notas_de_escrita or "—") if art else "—", ""]

    v = state.verdict
    p += ["## Judge (último veredito)"]
    if v is None:
        p += ["—", ""]
    else:
        for dim in (
            "alinhamento_objetivo", "discoverability", "concisao_clareza",
            "completude", "aderencia_best_practices",
        ):
            nota = getattr(v, dim)
            p += [f"- **{dim}:** {nota.nota:.2f} — {nota.rationale}"]
        p += ["", "**Feedback acionável:**", v.feedback_acionavel, ""]

    if state.historico:
        p += ["## Histórico de iterações", "", "| iter | score_final | det | judge |",
              "|------|-------------|-----|-------|"]
        for r in state.historico:
            p += [f"| {r.iteracao} | {r.score_final:.4f} | {r.score_det:.4f} | {r.score_judge:.4f} |"]
        p += [""]

    caminho = destino / "RUN.md"
    caminho.write_text("\n".join(p), encoding="utf-8")
    return caminho
