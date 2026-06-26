"""Schema e carregamento da configuração YAML do loopforge."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

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

    ``auto`` (default True): descobre os servers MCP da sessão do Claude Code
    (``~/.claude.json`` global + do projeto, e ``.mcp.json`` local) sem precisar
    configurar nada. ``config_path`` é um override opcional: aponta para um JSON
    no formato ``mcpServers`` e desliga a auto-descoberta. Cada server vira uma
    toolset prefixada pelo nome. ``agentes`` define quais nós recebem as tools
    (o Judge fica de fora por padrão para avaliar sem viés de ferramenta).
    """

    auto: bool = True
    config_path: str | None = None
    agentes: list[str] = Field(default_factory=lambda: ["discovery", "plan", "write"])
    incluir: list[str] | None = None  # allowlist de nomes de server (None = todos)
    excluir: list[str] = Field(default_factory=list)  # denylist de nomes de server

    @model_validator(mode="after")
    def _checa(self) -> McpCfg:
        invalidos = sorted(set(self.agentes) - _AGENTES_VALIDOS)
        if invalidos:
            raise ValueError(
                f"mcp.agentes inválidos: {invalidos}. Use um subconjunto de "
                f"{sorted(_AGENTES_VALIDOS)}."
            )
        return self


class WebsearchCfg(BaseModel):
    """Configuração da tool de web search dada aos agentes.

    Dá aos agentes uma tool para buscar conteúdo ATUALIZADO na internet durante
    o loop (best practices recentes, libs novas, etc.) — complementa o raciocínio
    da LLM de cada agente. ``provider`` escolhe o backend (``duckduckgo``, sem API
    key; ou ``tavily``, que lê ``TAVILY_API_KEY`` do ambiente). ``agentes`` define
    quais nós recebem a tool; ``max_results`` o teto por busca.

    Default: DuckDuckGo, ligado para os 4 agentes.
    """

    habilitado: bool = True
    provider: Literal["duckduckgo", "tavily"] = "duckduckgo"
    agentes: list[str] = Field(
        default_factory=lambda: ["discovery", "plan", "write", "judge"]
    )
    max_results: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _checa(self) -> WebsearchCfg:
        invalidos = sorted(set(self.agentes) - _AGENTES_VALIDOS)
        if invalidos:
            raise ValueError(
                f"websearch.agentes inválidos: {invalidos}. Use um subconjunto de "
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
    websearch: WebsearchCfg = Field(default_factory=WebsearchCfg)


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
