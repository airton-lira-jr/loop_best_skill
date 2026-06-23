"""Domain models e estado compartilhado do grafo LangGraph."""

from __future__ import annotations

from pydantic import BaseModel, Field

from loopforge.config import AppConfig


class Contexto(BaseModel):
    """Contexto herdado injetado nos agentes."""

    docs: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    best_practices_conteudo: str | None = None


class SkillPlan(BaseModel):
    """Spec da skill produzida pelo agente Plan."""

    name: str
    description: str
    estrutura: str
    arquivos: list[str] = Field(default_factory=list)
    justificativa: str


class SkillFile(BaseModel):
    """Arquivo referenciado pela skill (progressive disclosure)."""

    caminho: str
    conteudo: str


class SkillArtifact(BaseModel):
    """A skill escrita: SKILL.md + arquivos referenciados."""

    skill_md: str
    arquivos: list[SkillFile] = Field(default_factory=list)


class DimensaoNota(BaseModel):
    """Nota 0..1 de uma dimensão da rubrica do Judge."""

    nota: float = Field(ge=0.0, le=1.0)
    rationale: str


class JudgeVerdict(BaseModel):
    """Veredito estruturado do agente Judge."""

    alinhamento_objetivo: DimensaoNota
    discoverability: DimensaoNota
    concisao_clareza: DimensaoNota
    completude: DimensaoNota
    aderencia_best_practices: DimensaoNota
    feedback_acionavel: str


class IteracaoRegistro(BaseModel):
    """Registro de uma iteração do loop (para histórico e no-progress)."""

    iteracao: int
    score_final: float
    score_det: float
    score_judge: float


class LoopState(BaseModel):
    """Estado compartilhado que trafega entre os nós do grafo."""

    objetivo: str
    contexto: Contexto
    config: AppConfig
    discovery_report: str = ""
    plan: SkillPlan | None = None
    artifact: SkillArtifact | None = None
    verdict: JudgeVerdict | None = None
    score_final: float = 0.0
    score_det: float = 0.0
    score_judge: float = 0.0
    judge_feedback: str = ""
    iteracao: int = 0
    historico: list[IteracaoRegistro] = Field(default_factory=list)
    status: str = "running"
