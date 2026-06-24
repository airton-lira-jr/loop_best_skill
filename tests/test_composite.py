import pytest
from loopforge.config import JudgeCfg, PesosCfg
from loopforge.scoring.composite import score_composto
from loopforge.scoring.rubric import score_judge
from loopforge.state import DimensaoNota, JudgeVerdict


def _verdict(a, d, c, comp, ader):
    return JudgeVerdict(
        alinhamento_objetivo=DimensaoNota(nota=a, rationale=""),
        discoverability=DimensaoNota(nota=d, rationale=""),
        concisao_clareza=DimensaoNota(nota=c, rationale=""),
        completude=DimensaoNota(nota=comp, rationale=""),
        aderencia_best_practices=DimensaoNota(nota=ader, rationale=""),
        feedback_acionavel="",
    )


def test_score_judge_do_exemplo_do_readme():
    v = _verdict(0.90, 0.80, 0.70, 0.85, 0.90)
    assert score_judge(v, JudgeCfg(), best_practices_presente=True) == pytest.approx(0.840)


def test_score_judge_sem_best_practices_renormaliza():
    v = _verdict(1.0, 1.0, 1.0, 1.0, 0.0)  # aderencia deve ser ignorada
    assert score_judge(v, JudgeCfg(), best_practices_presente=False) == pytest.approx(1.0)


def test_score_composto_do_exemplo_do_readme():
    assert score_composto(0.902, 0.840, PesosCfg()) == pytest.approx(0.8586, abs=1e-4)
