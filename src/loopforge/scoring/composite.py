"""Combinação final do score híbrido."""

from __future__ import annotations

from loopforge.config import PesosCfg


def score_composto(score_det: float, score_judge: float, pesos: PesosCfg) -> float:
    """Combina o score determinístico e o do Judge.

    Args:
        score_det: score 0..1 da camada determinística.
        score_judge: score 0..1 da camada LLM-judge.
        pesos: pesos `deterministico` e `judge` (somam 1.0).

    Returns:
        score_final 0..1.
    """
    return pesos.deterministico * score_det + pesos.judge * score_judge
