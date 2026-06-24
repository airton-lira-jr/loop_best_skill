"""Schema e carregamento da configuração YAML do loopforge."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


def _soma_um(valores: list[float], rotulo: str) -> None:
    """Valida que uma lista de pesos soma ~1.0 (tolerância 1e-6)."""
    total = sum(valores)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"{rotulo}: pesos devem somar 1.0, somaram {total:.4f}")


class ModelCfg(BaseModel):
    """LLM provider and model identifier."""
    model: str


class AgentsCfg(BaseModel):
    """Configuration for discovery, plan, write, and judge agents."""
    discovery: ModelCfg
    plan: ModelCfg
    write: ModelCfg
    judge: ModelCfg


class SkillCfg(BaseModel):
    objetivo: str
    output_dir: str = "./skills"
    best_practices: str | None = None


class LoopCfg(BaseModel):
    max_iteracoes: int = Field(default=6, ge=1)
    score_minimo: float = Field(default=0.8, ge=0.0, le=1.0)
    no_progress_paciencia: int = Field(default=2, ge=1)


class PesosCfg(BaseModel):
    deterministico: float = 0.30
    judge: float = 0.70

    @model_validator(mode="after")
    def _checa(self) -> PesosCfg:
        _soma_um([self.deterministico, self.judge], "scoring.pesos")
        return self


class DeterministicoCfg(BaseModel):
    frontmatter_valido: float = 0.25
    description_tem_trigger: float = 0.25
    dentro_budget: float = 0.20
    refs_existem: float = 0.15
    markdown_valido: float = 0.15
    budget_linhas: int = Field(default=500, ge=1)

    @model_validator(mode="after")
    def _checa(self) -> DeterministicoCfg:
        _soma_um(
            [self.frontmatter_valido, self.description_tem_trigger, self.dentro_budget,
             self.refs_existem, self.markdown_valido],
            "scoring.deterministico",
        )
        return self


class JudgeCfg(BaseModel):
    alinhamento_objetivo: float = 0.30
    discoverability: float = 0.20
    concisao_clareza: float = 0.15
    completude: float = 0.20
    aderencia_best_practices: float = 0.15

    @model_validator(mode="after")
    def _checa(self) -> JudgeCfg:
        _soma_um(
            [self.alinhamento_objetivo, self.discoverability, self.concisao_clareza,
             self.completude, self.aderencia_best_practices],
            "scoring.judge",
        )
        return self


class ScoringCfg(BaseModel):
    pesos: PesosCfg = Field(default_factory=PesosCfg)
    deterministico: DeterministicoCfg = Field(default_factory=DeterministicoCfg)
    judge: JudgeCfg = Field(default_factory=JudgeCfg)


class ContextoCfg(BaseModel):
    """External documentation and reference links for agent context."""
    docs: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


_AGENTES_VALIDOS = {"discovery", "plan", "write", "judge"}


class McpCfg(BaseModel):
    """Configuração de servidores MCP disponibilizados como tools aos agentes.

    ``config_path`` aponta para um JSON no formato ``mcpServers`` (o mesmo do
    Claude Desktop/Cursor/Claude Code); cada server vira uma toolset prefixada
    pelo nome do server. ``agentes`` define quais nós recebem essas tools (o
    Judge fica de fora por padrão para avaliar sem viés de ferramenta).
    """

    config_path: str | None = None
    agentes: list[str] = Field(default_factory=lambda: ["discovery", "plan", "write"])

    @model_validator(mode="after")
    def _checa(self) -> McpCfg:
        invalidos = sorted(set(self.agentes) - _AGENTES_VALIDOS)
        if invalidos:
            raise ValueError(
                f"mcp.agentes inválidos: {invalidos}. Use um subconjunto de "
                f"{sorted(_AGENTES_VALIDOS)}."
            )
        return self


class AppConfig(BaseModel):
    """Root configuration schema for loopforge application."""
    agents: AgentsCfg
    skill: SkillCfg
    loop: LoopCfg = Field(default_factory=LoopCfg)
    scoring: ScoringCfg = Field(default_factory=ScoringCfg)
    contexto: ContextoCfg = Field(default_factory=ContextoCfg)
    mcp: McpCfg = Field(default_factory=McpCfg)


def load_config(path: str | Path) -> AppConfig:
    """Lê e valida o YAML de configuração.

    Args:
        path: caminho do arquivo YAML.

    Returns:
        AppConfig validado (com defaults aplicados).

    Raises:
        FileNotFoundError: se o arquivo não existe.
        pydantic.ValidationError: se o schema ou os pesos forem inválidos.
    """
    texto = Path(path).read_text(encoding="utf-8")
    dados = yaml.safe_load(texto) or {}
    return AppConfig.model_validate(dados)
