"""Domain models e estado compartilhado do grafo LangGraph."""

from __future__ import annotations

from pydantic import BaseModel, Field

from loopforge.config import AppConfig


class FonteConteudo(BaseModel):
    """Conteúdo lido de uma fonte de referência (arquivo de doc ou URL)."""

    origem: str
    conteudo: str


class Contexto(BaseModel):
    """Contexto herdado injetado nos agentes.

    ``docs`` e ``links`` guardam os identificadores brutos (paths/URLs);
    ``docs_conteudo`` e ``links_conteudo`` guardam o conteúdo já lido/baixado
    dessas fontes, que é o que de fato vai para o prompt dos agentes.
    """

    docs: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    best_practices_conteudo: str | None = None
    docs_conteudo: list[FonteConteudo] = Field(default_factory=list)
    links_conteudo: list[FonteConteudo] = Field(default_factory=list)


class Abordagem(BaseModel):
    """Uma abordagem candidata levantada pelo Discovery para atingir o objetivo."""

    nome: str
    resumo: str
    pros: list[str] = Field(default_factory=list)
    contras: list[str] = Field(default_factory=list)
    adequacao: float = Field(ge=0.0, le=1.0)  # quão bem atinge o objetivo (0..1)
    data_atualizacao: str = ""  # quão recente é o conhecimento (ex: "2026-06" ou "v3.1")


class DiscoveryReport(BaseModel):
    """Saída do Discovery: pesquisa + abordagens + a recomendada (com justificativa).

    ``achados`` e ``fontes`` são a TRILHA de pesquisa que o Discovery documenta para
    os agentes seguintes: o que foi descoberto na web/MCP e de onde veio. Sem isso a
    pesquisa evapora e o Plan/Write/Judge perdem a fundamentação.
    """

    achados: list[str] = Field(default_factory=list)  # fatos/insights da pesquisa
    fontes: list[str] = Field(default_factory=list)  # URLs/docs/MCP consultados
    abordagens: list[Abordagem] = Field(default_factory=list)
    recomendada: str  # nome da abordagem escolhida
    justificativa: str


class SkillPlan(BaseModel):
    """Spec da skill produzida pelo agente Plan.

    ``secoes`` e ``notas_para_write`` documentam as DECISÕES do Plan para o Write:
    quais seções o corpo do SKILL.md deve ter e quais decisões/cuidados o escritor
    precisa respeitar (ex: usar progressive disclosure só na parte X, citar a fonte Y).
    """

    name: str
    description: str
    estrutura: str
    secoes: list[str] = Field(default_factory=list)  # seções planejadas do corpo
    arquivos: list[str] = Field(default_factory=list)
    notas_para_write: str = ""  # decisões/cuidados que o Write deve respeitar
    justificativa: str


class SkillFile(BaseModel):
    """Arquivo referenciado pela skill (progressive disclosure)."""

    caminho: str
    conteudo: str


class SkillArtifact(BaseModel):
    """A skill escrita: SKILL.md + arquivos referenciados.

    ``notas_de_escrita`` documenta o que o Write fez e por quê (decisões de
    estrutura, como o feedback do Judge foi endereçado): é o que o Judge lê para
    avaliar com contexto, não só o texto final.
    """

    skill_md: str
    arquivos: list[SkillFile] = Field(default_factory=list)
    notas_de_escrita: str = ""  # decisões de escrita + como o feedback foi tratado


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
    problemas_bloqueantes: list[str] = Field(default_factory=list)
    sugestoes: list[str] = Field(default_factory=list)


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
    discovery_report: DiscoveryReport | None = None
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
