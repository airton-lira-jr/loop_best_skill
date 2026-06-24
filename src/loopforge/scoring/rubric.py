"""Camada LLM-judge do score: média ponderada da rubrica do Judge."""

from __future__ import annotations

from loopforge.config import JudgeCfg
from loopforge.state import JudgeVerdict


def score_judge(verdict: JudgeVerdict, cfg: JudgeCfg, best_practices_presente: bool) -> float:
    """Calcula o score do Judge como média ponderada das dimensões.

    Args:
        verdict: notas 0..1 por dimensão.
        cfg: pesos das dimensões.
        best_practices_presente: se False, ignora `aderencia_best_practices`
            e renormaliza os pesos das 4 dimensões restantes.

    Returns:
        Score 0..1.
    """
    pares = [
        (verdict.alinhamento_objetivo.nota, cfg.alinhamento_objetivo),
        (verdict.discoverability.nota, cfg.discoverability),
        (verdict.concisao_clareza.nota, cfg.concisao_clareza),
        (verdict.completude.nota, cfg.completude),
    ]
    if best_practices_presente:
        pares.append((verdict.aderencia_best_practices.nota, cfg.aderencia_best_practices))

    soma_pesos = sum(peso for _, peso in pares)
    return sum(nota * peso for nota, peso in pares) / soma_pesos
