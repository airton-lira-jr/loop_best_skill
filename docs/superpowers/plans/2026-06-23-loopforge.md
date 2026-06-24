# Loop Engineer (`loopforge`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App Python que roda um loop multi-agente (LLMs distintas) e gera uma SKILL do Claude até atingir um score de qualidade ou um teto de iterações.

**Architecture:** LangGraph orquestra 4 nós PydanticAI (`Discovery → Plan → Write → Judge`) com aresta de loop condicional. A métrica é um score composto híbrido (checks determinísticos + LLM-as-judge rubricado). Estado em Pydantic, persistido por checkpointer SQLite (memory spine + time-travel no Studio).

**Tech Stack:** Python 3.11+, uv, PydanticAI, LangGraph, langgraph-cli, Typer, Rich, structlog, PyYAML, pytest.

## Global Constraints

- Python `>=3.11`.
- Gerenciador: **uv** (`uv sync`, `uv run`, `uv add`). Nunca usar pip direto.
- Formato de `model`: string PydanticAI `provider:modelo` (ex: `anthropic:claude-opus-4-8`, `google-gla:gemini-2.0-flash`).
- Anti-viés (default): `agents.judge.model` usa provider **≠** `agents.write.model`.
- Pesos: `scoring.pesos` soma 1.0; `scoring.deterministico` (5 checks) soma 1.0; `scoring.judge` (5 dims) soma 1.0. Validar na carga.
- Toda função pública tem docstring (estilo Google) e type hints.
- TDD: teste falha → implementa → passa → commit. Commits frequentes, um por tarefa.
- Agentes nunca chamam API real em teste: usar `TestModel`/`FunctionModel` do PydanticAI via `agent.override(model=...)`.
- **Verificar as APIs de PydanticAI/LangGraph contra a versão instalada** (`uv run python -c "import pydantic_ai, langgraph; print(pydantic_ai.__version__)"`); ajustar nomes (`output_type`/`result_type`, `.output`/`.data`) se a versão divergir do código abaixo (escrito p/ PydanticAI 1.x).
- Não commitar sem o passo de commit explícito de cada tarefa.

---

### Task 1: Scaffold do projeto (uv + pacote + pytest)

**Files:**
- Create: `pyproject.toml`
- Create: `src/loopforge/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Produces: pacote importável `loopforge` (`__version__`); `uv run pytest` funcional; entry point `loopforge = "loopforge.cli:app"`.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_pacote_importa_e_tem_versao():
    import loopforge

    assert isinstance(loopforge.__version__, str)
    assert loopforge.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'loopforge'`).

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:
```toml
[project]
name = "loopforge"
version = "0.1.0"
description = "Loop Engineer: multi-agent loop que gera SKILLs do Claude"
requires-python = ">=3.11"
dependencies = [
    "pydantic-ai>=1.0",
    "langgraph>=0.2",
    "langgraph-cli[inmem]>=0.1",
    "langgraph-checkpoint-sqlite>=2.0",
    "pyyaml>=6.0",
    "typer>=0.12",
    "rich>=13.7",
    "structlog>=24.1",
]

[project.scripts]
loopforge = "loopforge.cli:app"

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "anyio>=4.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/loopforge"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
testpaths = ["tests"]
```

`src/loopforge/__init__.py`:
```python
"""Loop Engineer: orquestração multi-agente que gera SKILLs do Claude."""

__version__ = "0.1.0"
```

`tests/__init__.py`: arquivo vazio.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/loopforge/__init__.py tests/
git commit -m "chore: scaffold loopforge (uv + pacote + pytest)"
```

---

### Task 2: Schema de configuração + loader + validação

**Files:**
- Create: `src/loopforge/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - Models Pydantic: `ModelCfg(model:str)`, `AgentsCfg(discovery,plan,write,judge: ModelCfg)`, `SkillCfg(objetivo:str, output_dir:str="./skills", best_practices:str|None=None)`, `LoopCfg(max_iteracoes:int=6, score_minimo:float=0.8, no_progress_paciencia:int=2)`, `PesosCfg(deterministico:float=0.30, judge:float=0.70)`, `DeterministicoCfg(frontmatter_valido=0.25, description_tem_trigger=0.25, dentro_budget=0.20, refs_existem=0.15, markdown_valido=0.15, budget_linhas:int=500)`, `JudgeCfg(alinhamento_objetivo=0.30, discoverability=0.20, concisao_clareza=0.15, completude=0.20, aderencia_best_practices=0.15)`, `ScoringCfg(pesos:PesosCfg, deterministico:DeterministicoCfg, judge:JudgeCfg)`, `ContextoCfg(docs:list[str]=[], links:list[str]=[])`, `AppConfig(agents,skill,loop,scoring,contexto)`.
  - `load_config(path: str | Path) -> AppConfig`.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import textwrap
import pytest
from pydantic import ValidationError
from loopforge.config import load_config


def _write(tmp_path, body: str):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_load_config_minimo_aplica_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, """
        agents:
          discovery: {model: google-gla:gemini-2.0-flash}
          plan:      {model: anthropic:claude-opus-4-8}
          write:     {model: anthropic:claude-opus-4-8}
          judge:     {model: google-gla:gemini-2.0-flash}
        skill:
          objetivo: "Gerar uma skill de review de PR"
    """))
    assert cfg.skill.output_dir == "./skills"
    assert cfg.loop.max_iteracoes == 6
    assert cfg.scoring.pesos.deterministico == 0.30
    assert cfg.scoring.deterministico.budget_linhas == 500


def test_pesos_que_nao_somam_um_falham(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, """
            agents:
              discovery: {model: google-gla:gemini-2.0-flash}
              plan:      {model: anthropic:claude-opus-4-8}
              write:     {model: anthropic:claude-opus-4-8}
              judge:     {model: google-gla:gemini-2.0-flash}
            skill: {objetivo: "x"}
            scoring:
              pesos: {deterministico: 0.5, judge: 0.9}
        """))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: loopforge.config`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/config.py`:
```python
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
    model: str


class AgentsCfg(BaseModel):
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
    def _checa(self) -> "PesosCfg":
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
    def _checa(self) -> "DeterministicoCfg":
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
    def _checa(self) -> "JudgeCfg":
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
    docs: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    agents: AgentsCfg
    skill: SkillCfg
    loop: LoopCfg = Field(default_factory=LoopCfg)
    scoring: ScoringCfg = Field(default_factory=ScoringCfg)
    contexto: ContextoCfg = Field(default_factory=ContextoCfg)


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/config.py tests/test_config.py
git commit -m "feat: schema + loader de configuração YAML com validação de pesos"
```

---

### Task 3: Domain models + estado do grafo

**Files:**
- Create: `src/loopforge/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `AppConfig`, `ContextoCfg` (de `config.py`).
- Produces:
  - `Contexto(docs:list[str], links:list[str], best_practices_conteudo:str|None=None)`
  - `SkillPlan(name:str, description:str, estrutura:str, arquivos:list[str], justificativa:str)`
  - `SkillFile(caminho:str, conteudo:str)`
  - `SkillArtifact(skill_md:str, arquivos:list[SkillFile]=[])`
  - `DimensaoNota(nota:float, rationale:str)`
  - `JudgeVerdict(alinhamento_objetivo, discoverability, concisao_clareza, completude, aderencia_best_practices: DimensaoNota, feedback_acionavel:str)`
  - `IteracaoRegistro(iteracao:int, score_final:float, score_det:float, score_judge:float)`
  - `LoopState(objetivo:str, contexto:Contexto, config:AppConfig, discovery_report:str="", plan:SkillPlan|None=None, artifact:SkillArtifact|None=None, verdict:JudgeVerdict|None=None, score_final:float=0.0, score_det:float=0.0, score_judge:float=0.0, judge_feedback:str="", iteracao:int=0, historico:list[IteracaoRegistro]=[], status:str="running")`

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
from loopforge.state import (
    DimensaoNota, JudgeVerdict, SkillArtifact, SkillFile, SkillPlan,
)


def test_skill_artifact_aceita_arquivos():
    art = SkillArtifact(
        skill_md="---\nname: x\ndescription: Use quando...\n---\n# X\n",
        arquivos=[SkillFile(caminho="references/a.md", conteudo="...")],
    )
    assert art.arquivos[0].caminho == "references/a.md"


def test_judge_verdict_dimensoes_tipadas():
    v = JudgeVerdict(
        alinhamento_objetivo=DimensaoNota(nota=0.9, rationale="ok"),
        discoverability=DimensaoNota(nota=0.8, rationale="ok"),
        concisao_clareza=DimensaoNota(nota=0.7, rationale="ok"),
        completude=DimensaoNota(nota=0.85, rationale="ok"),
        aderencia_best_practices=DimensaoNota(nota=0.9, rationale="ok"),
        feedback_acionavel="melhore a description",
    )
    assert 0.0 <= v.discoverability.nota <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL (`ModuleNotFoundError: loopforge.state`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/state.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/state.py tests/test_state.py
git commit -m "feat: domain models e estado do grafo"
```

---

### Task 4: Carregador de contexto (docs/links/best_practices)

**Files:**
- Create: `src/loopforge/context.py`
- Test: `tests/test_context.py`

**Interfaces:**
- Consumes: `Contexto` (state.py), `AppConfig`/`ContextoCfg` (config.py).
- Produces: `build_contexto(config: AppConfig, extra_docs: list[str] | None = None, extra_links: list[str] | None = None) -> Contexto` — funde docs/links do YAML com os extras da CLI e lê o conteúdo do arquivo `skill.best_practices` (se houver).

- [ ] **Step 1: Write the failing test**

`tests/test_context.py`:
```python
from loopforge.config import AppConfig
from loopforge.context import build_contexto

BASE = {
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
}


def test_funde_docs_da_cli_com_yaml():
    cfg = AppConfig.model_validate({**BASE, "contexto": {"docs": ["./d1"], "links": ["http://a"]}})
    ctx = build_contexto(cfg, extra_docs=["./d2"], extra_links=["http://b"])
    assert ctx.docs == ["./d1", "./d2"]
    assert ctx.links == ["http://a", "http://b"]
    assert ctx.best_practices_conteudo is None


def test_le_best_practices_quando_existe(tmp_path):
    bp = tmp_path / "SKILL.md"
    bp.write_text("regras asaas", encoding="utf-8")
    cfg = AppConfig.model_validate({**BASE, "skill": {"objetivo": "x", "best_practices": str(bp)}})
    ctx = build_contexto(cfg)
    assert ctx.best_practices_conteudo == "regras asaas"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_context.py -v`
Expected: FAIL (`ModuleNotFoundError: loopforge.context`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/context.py`:
```python
"""Montagem do contexto herdado injetado nos agentes."""

from __future__ import annotations

from pathlib import Path

from loopforge.config import AppConfig
from loopforge.state import Contexto


def build_contexto(
    config: AppConfig,
    extra_docs: list[str] | None = None,
    extra_links: list[str] | None = None,
) -> Contexto:
    """Funde contexto do YAML com extras da CLI e lê o best_practices SKILL.

    Args:
        config: configuração carregada.
        extra_docs: diretórios de doc passados via `--doc` (estendem o YAML).
        extra_links: URLs passadas via `--link` (estendem o YAML).

    Returns:
        Contexto pronto para injeção nos prompts dos agentes.
    """
    docs = [*config.contexto.docs, *(extra_docs or [])]
    links = [*config.contexto.links, *(extra_links or [])]

    bp_conteudo: str | None = None
    if config.skill.best_practices:
        caminho = Path(config.skill.best_practices)
        if caminho.exists():
            bp_conteudo = caminho.read_text(encoding="utf-8")

    return Contexto(docs=docs, links=links, best_practices_conteudo=bp_conteudo)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_context.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/context.py tests/test_context.py
git commit -m "feat: carregador de contexto (docs/links/best_practices)"
```

---

### Task 5: Scorer determinístico

**Files:**
- Create: `src/loopforge/scoring/__init__.py`
- Create: `src/loopforge/scoring/deterministic.py`
- Test: `tests/test_deterministic.py`

**Interfaces:**
- Consumes: `SkillArtifact` (state.py), `DeterministicoCfg` (config.py).
- Produces: `score_deterministico(artifact: SkillArtifact, cfg: DeterministicoCfg) -> tuple[float, dict[str, float]]` — retorna `(score 0..1, detalhes por check)`. Checks: `frontmatter_valido`, `description_tem_trigger`, `dentro_budget`, `refs_existem`, `markdown_valido`.

- [ ] **Step 1: Write the failing test**

`tests/test_deterministic.py`:
```python
from loopforge.config import DeterministicoCfg
from loopforge.scoring.deterministic import score_deterministico
from loopforge.state import SkillArtifact, SkillFile

CFG = DeterministicoCfg()

SKILL_OK = (
    "---\n"
    "name: pr-review\n"
    "description: Use quando precisar revisar PRs de Python.\n"
    "---\n"
    "# PR Review\n\n"
    "Veja [refs](references/guia.md).\n"
)


def test_skill_perfeita_pontua_1():
    art = SkillArtifact(skill_md=SKILL_OK, arquivos=[SkillFile(caminho="references/guia.md", conteudo="x")])
    score, detalhes = score_deterministico(art, CFG)
    assert score == 1.0
    assert detalhes["frontmatter_valido"] == 1.0


def test_sem_trigger_perde_o_peso():
    skill = SKILL_OK.replace("Use quando precisar revisar PRs de Python.", "Revisor de PRs.")
    art = SkillArtifact(skill_md=skill, arquivos=[SkillFile(caminho="references/guia.md", conteudo="x")])
    score, detalhes = score_deterministico(art, CFG)
    assert detalhes["description_tem_trigger"] == 0.0
    assert score == 1.0 - CFG.description_tem_trigger


def test_budget_excedido_penaliza_proporcional():
    corpo = "\n".join(f"linha {i}" for i in range(620))
    skill = f"---\nname: x\ndescription: Use quando algo.\n---\n{corpo}\n"
    art = SkillArtifact(skill_md=skill)  # sem refs => refs_existem = 1.0
    score, detalhes = score_deterministico(art, DeterministicoCfg(budget_linhas=500))
    assert round(detalhes["dentro_budget"], 3) == round(max(0.0, 1 - (skill.count(chr(10)) + 1 - 500) / 500), 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deterministic.py -v`
Expected: FAIL (`ModuleNotFoundError: loopforge.scoring`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/scoring/__init__.py`: arquivo vazio com docstring `"""Camadas de pontuação da skill."""`.

`src/loopforge/scoring/deterministic.py`:
```python
"""Camada determinística do score: checks programáticos sobre a skill."""

from __future__ import annotations

import re

import yaml

from loopforge.config import DeterministicoCfg
from loopforge.state import SkillArtifact

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TRIGGER = re.compile(r"use\s+(when|quando)", re.IGNORECASE)
_REF_LINK = re.compile(r"\]\(([^)]+\.\w+)\)")


def _parse_frontmatter(skill_md: str) -> dict | None:
    """Extrai e parseia o frontmatter YAML; None se ausente/inválido."""
    m = _FRONTMATTER.match(skill_md)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


def score_deterministico(
    artifact: SkillArtifact, cfg: DeterministicoCfg
) -> tuple[float, dict[str, float]]:
    """Pontua a skill com checks determinísticos.

    Args:
        artifact: skill escrita.
        cfg: pesos e budget de linhas.

    Returns:
        (score 0..1, dict com a contribuição 0..1 de cada check antes do peso).
    """
    fm = _parse_frontmatter(artifact.skill_md)
    detalhes: dict[str, float] = {}

    detalhes["frontmatter_valido"] = 1.0 if fm and "name" in fm and "description" in fm else 0.0

    descricao = str(fm.get("description", "")) if fm else ""
    detalhes["description_tem_trigger"] = 1.0 if _TRIGGER.search(descricao) else 0.0

    linhas = artifact.skill_md.count("\n") + 1
    if linhas <= cfg.budget_linhas:
        detalhes["dentro_budget"] = 1.0
    else:
        detalhes["dentro_budget"] = max(0.0, 1 - (linhas - cfg.budget_linhas) / cfg.budget_linhas)

    referenciados = set(_REF_LINK.findall(artifact.skill_md))
    if not referenciados:
        detalhes["refs_existem"] = 1.0
    else:
        presentes = {f.caminho for f in artifact.arquivos}
        existentes = sum(1 for r in referenciados if r in presentes)
        detalhes["refs_existem"] = existentes / len(referenciados)

    tem_heading = bool(re.search(r"^#\s", artifact.skill_md, re.MULTILINE))
    detalhes["markdown_valido"] = 1.0 if (fm is not None and tem_heading) else 0.0

    score = (
        cfg.frontmatter_valido * detalhes["frontmatter_valido"]
        + cfg.description_tem_trigger * detalhes["description_tem_trigger"]
        + cfg.dentro_budget * detalhes["dentro_budget"]
        + cfg.refs_existem * detalhes["refs_existem"]
        + cfg.markdown_valido * detalhes["markdown_valido"]
    )
    return score, detalhes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deterministic.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/scoring/__init__.py src/loopforge/scoring/deterministic.py tests/test_deterministic.py
git commit -m "feat: scorer determinístico (frontmatter, trigger, budget, refs, markdown)"
```

---

### Task 6: Scorer do Judge (rubrica) + score composto

**Files:**
- Create: `src/loopforge/scoring/rubric.py`
- Create: `src/loopforge/scoring/composite.py`
- Test: `tests/test_composite.py`

**Interfaces:**
- Consumes: `JudgeVerdict` (state.py), `JudgeCfg`/`PesosCfg` (config.py).
- Produces:
  - `score_judge(verdict: JudgeVerdict, cfg: JudgeCfg, best_practices_presente: bool) -> float` — média ponderada das 5 dims; se `best_practices_presente=False`, dropa `aderencia_best_practices` e **renormaliza** os 4 pesos restantes.
  - `score_composto(score_det: float, score_judge: float, pesos: PesosCfg) -> float`.

- [ ] **Step 1: Write the failing test**

`tests/test_composite.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_composite.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/scoring/rubric.py`:
```python
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
```

`src/loopforge/scoring/composite.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_composite.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/scoring/rubric.py src/loopforge/scoring/composite.py tests/test_composite.py
git commit -m "feat: score do Judge (rubrica + renormalização) e score composto"
```

---

### Task 7: Agentes PydanticAI (discovery, plan, write, judge)

**Files:**
- Create: `src/loopforge/agents/__init__.py`
- Create: `src/loopforge/agents/prompts.py`
- Create: `src/loopforge/agents/builder.py`
- Test: `tests/test_agents.py`

**Interfaces:**
- Consumes: `AppConfig` (config.py); models de `state.py` (`SkillPlan`, `SkillArtifact`, `JudgeVerdict`).
- Produces:
  - `AgentsBundle(discovery, plan, write, judge: Agent)` (dataclass).
  - `build_agents(config: AppConfig) -> AgentsBundle` — cria 1 `Agent` por nó: `discovery` (output `str`), `plan` (output `SkillPlan`), `write` (output `SkillArtifact`), `judge` (output `JudgeVerdict`), cada um com o `model` do YAML e system prompt de `prompts.py`.
  - `prompts.py`: constantes `DISCOVERY_SYS`, `PLAN_SYS`, `WRITE_SYS`, `JUDGE_SYS`.

- [ ] **Step 1: Write the failing test**

`tests/test_agents.py`:
```python
import pytest
from pydantic_ai.models.test import TestModel

from loopforge.agents.builder import build_agents
from loopforge.config import AppConfig
from loopforge.state import JudgeVerdict, SkillArtifact, SkillPlan

CFG = AppConfig.model_validate({
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
})


def test_build_agents_cria_os_quatro():
    bundle = build_agents(CFG)
    assert {"discovery", "plan", "write", "judge"} <= set(vars(bundle))


@pytest.mark.anyio
async def test_plan_agent_produz_skillplan_tipado():
    bundle = build_agents(CFG)
    with bundle.plan.override(model=TestModel()):
        res = await bundle.plan.run("planeje uma skill")
    assert isinstance(res.output, SkillPlan)


@pytest.mark.anyio
async def test_write_e_judge_produzem_tipos():
    bundle = build_agents(CFG)
    with bundle.write.override(model=TestModel()):
        w = await bundle.write.run("escreva")
    with bundle.judge.override(model=TestModel()):
        j = await bundle.judge.run("avalie")
    assert isinstance(w.output, SkillArtifact)
    assert isinstance(j.output, JudgeVerdict)
```

(Se a versão instalada não tiver `anyio_mode=auto` resolvendo `@pytest.mark.anyio`, trocar por `@pytest.mark.asyncio`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents.py -v`
Expected: FAIL (`ModuleNotFoundError: loopforge.agents`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/agents/__init__.py`: docstring `"""Agentes PydanticAI do loop."""`.

`src/loopforge/agents/prompts.py`:
```python
"""System prompts dos agentes do loop (regras embutidas das best practices de skills)."""

DISCOVERY_SYS = (
    "Você é o agente de Discovery. Pesquise soluções, tecnologias e estratégias para "
    "atingir o objetivo da SKILL. Seja conciso e cite caminhos concretos. "
    "Retorne um relatório em texto com as melhores abordagens."
)

PLAN_SYS = (
    "Você é o agente de Plan. A partir do relatório de discovery, produza a SPEC de uma "
    "SKILL do Claude. Regras: a `description` DEVE conter um gatilho de uso ('Use quando…'); "
    "prefira regra+porquê a imperativos; planeje progressive disclosure (arquivos referenciados) "
    "só quando reduzir tokens. Incorpore o feedback do Judge quando houver."
)

WRITE_SYS = (
    "Você é o agente de Write. Escreva a SKILL do Claude conforme o plano. Produza o `SKILL.md` "
    "completo (frontmatter YAML com `name` e `description` + corpo) e os arquivos referenciados. "
    "Seja conciso: cada token compete com o contexto."
)

JUDGE_SYS = (
    "Você é o agente Judge. Avalie a SKILL contra o objetivo e as best practices fornecidas. "
    "Dê nota 0..1 por dimensão (alinhamento ao objetivo, discoverability, concisão/clareza, "
    "completude, aderência às best practices) com rationale curto, e um feedback acionável para "
    "a próxima iteração. Seja rigoroso e calibrado."
)
```

`src/loopforge/agents/builder.py`:
```python
"""Construção dos agentes PydanticAI a partir da configuração."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from loopforge.agents.prompts import DISCOVERY_SYS, JUDGE_SYS, PLAN_SYS, WRITE_SYS
from loopforge.config import AppConfig
from loopforge.state import JudgeVerdict, SkillArtifact, SkillPlan


@dataclass
class AgentsBundle:
    """Conjunto dos 4 agentes do loop."""

    discovery: Agent
    plan: Agent
    write: Agent
    judge: Agent


def build_agents(config: AppConfig) -> AgentsBundle:
    """Cria um Agent PydanticAI por nó, com o modelo do YAML e output tipado.

    Args:
        config: configuração carregada (fornece o `model` de cada agente).

    Returns:
        AgentsBundle com discovery/plan/write/judge.
    """
    return AgentsBundle(
        discovery=Agent(config.agents.discovery.model, system_prompt=DISCOVERY_SYS),
        plan=Agent(config.agents.plan.model, system_prompt=PLAN_SYS, output_type=SkillPlan),
        write=Agent(config.agents.write.model, system_prompt=WRITE_SYS, output_type=SkillArtifact),
        judge=Agent(config.agents.judge.model, system_prompt=JUDGE_SYS, output_type=JudgeVerdict),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agents.py -v`
Expected: PASS (3 testes). Se `output_type` não existir na versão instalada, usar `result_type`.

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/agents/ tests/test_agents.py
git commit -m "feat: agentes PydanticAI (discovery/plan/write/judge) com output tipado"
```

---

### Task 8: Logging estruturado (structlog + rich)

**Files:**
- Create: `src/loopforge/logging.py`
- Test: `tests/test_logging.py`

**Interfaces:**
- Produces: `setup_logging(verbose: bool = False) -> None`; `get_logger(nome: str) -> structlog.BoundLogger`.

- [ ] **Step 1: Write the failing test**

`tests/test_logging.py`:
```python
from loopforge.logging import get_logger, setup_logging


def test_logger_emite_evento(capsys):
    setup_logging()
    log = get_logger("teste")
    log.info("no_avancou", iteracao=1, score=0.5)
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "no_avancou" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_logging.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/logging.py`:
```python
"""Configuração de logging estruturado com structlog + rich."""

from __future__ import annotations

import logging

import structlog
from rich.logging import RichHandler


def setup_logging(verbose: bool = False) -> None:
    """Configura structlog sobre o logging padrão com saída Rich.

    Args:
        verbose: se True, nível DEBUG; senão INFO.
    """
    nivel = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=nivel,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(nivel),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )


def get_logger(nome: str) -> structlog.BoundLogger:
    """Retorna um logger structlog nomeado.

    Args:
        nome: nome do logger (geralmente o nó do grafo).

    Returns:
        Logger estruturado.
    """
    return structlog.get_logger(nome)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_logging.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/logging.py tests/test_logging.py
git commit -m "feat: logging estruturado (structlog + rich)"
```

---

### Task 9: Grafo LangGraph + nós + controle de loop

**Files:**
- Create: `src/loopforge/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `LoopState`, models (state.py); `AgentsBundle`/`build_agents` (agents/builder.py); scorers (scoring/*); `build_contexto` indiretamente (estado já traz `Contexto`); `get_logger` (logging.py).
- Produces:
  - `decidir_loop(state: LoopState) -> str` — retorna `"aprovado"`, `"reitera"` ou `"para"` conforme score / max_iter / no-progress.
  - `build_builder(config: AppConfig, agents: AgentsBundle | None = None) -> StateGraph` — monta nós e arestas (sem compilar).
  - `build_graph(config: AppConfig, agents: AgentsBundle | None = None, checkpointer=None)` — compila o builder.
  - Nós async: `discovery_node`, `plan_node`, `write_node`, `judge_node` (definidos como closures dentro de `build_builder`, capturando `agents` e `config`).

- [ ] **Step 1: Write the failing test**

`tests/test_graph.py`:
```python
import pytest
from pydantic_ai.models.test import TestModel

from loopforge.agents.builder import build_agents
from loopforge.config import AppConfig
from loopforge.graph import build_graph, decidir_loop
from loopforge.state import Contexto, IteracaoRegistro, LoopState

CFG = AppConfig.model_validate({
    "agents": {
        "discovery": {"model": "google-gla:gemini-2.0-flash"},
        "plan": {"model": "anthropic:claude-opus-4-8"},
        "write": {"model": "anthropic:claude-opus-4-8"},
        "judge": {"model": "google-gla:gemini-2.0-flash"},
    },
    "skill": {"objetivo": "x"},
    "loop": {"max_iteracoes": 3, "score_minimo": 0.8, "no_progress_paciencia": 2},
})


def _state(**kw):
    base = dict(objetivo="x", contexto=Contexto(), config=CFG)
    base.update(kw)
    return LoopState(**base)


def test_decidir_aprovado():
    assert decidir_loop(_state(score_final=0.85, iteracao=1)) == "aprovado"


def test_decidir_para_no_max_iter():
    assert decidir_loop(_state(score_final=0.5, iteracao=3)) == "para"


def test_decidir_para_por_estagnacao():
    hist = [IteracaoRegistro(iteracao=1, score_final=0.50, score_det=0, score_judge=0),
            IteracaoRegistro(iteracao=2, score_final=0.50, score_det=0, score_judge=0)]
    assert decidir_loop(_state(score_final=0.50, iteracao=2, historico=hist)) == "para"


def test_decidir_reitera():
    hist = [IteracaoRegistro(iteracao=1, score_final=0.40, score_det=0, score_judge=0)]
    assert decidir_loop(_state(score_final=0.60, iteracao=1, historico=hist)) == "reitera"


@pytest.mark.anyio
async def test_grafo_roda_ate_aprovar_com_testmodel():
    # Judge sempre devolve notas altas via TestModel(custom_output_args) → aprova na 1ª volta.
    bundle = build_agents(CFG)
    judge_out = {
        "alinhamento_objetivo": {"nota": 0.95, "rationale": "ok"},
        "discoverability": {"nota": 0.95, "rationale": "ok"},
        "concisao_clareza": {"nota": 0.95, "rationale": "ok"},
        "completude": {"nota": 0.95, "rationale": "ok"},
        "aderencia_best_practices": {"nota": 0.95, "rationale": "ok"},
        "feedback_acionavel": "nada",
    }
    write_out = {
        "skill_md": "---\nname: x\ndescription: Use quando testar.\n---\n# X\n",
        "arquivos": [],
    }
    with bundle.discovery.override(model=TestModel()), \
         bundle.plan.override(model=TestModel()), \
         bundle.write.override(model=TestModel(custom_output_args=write_out)), \
         bundle.judge.override(model=TestModel(custom_output_args=judge_out)):
        graph = build_graph(CFG, agents=bundle)
        final = await graph.ainvoke(LoopState(objetivo="x", contexto=Contexto(), config=CFG))
    assert final["status"] == "aprovado"
    assert final["score_final"] >= 0.8
```

(`graph.ainvoke` devolve dict-like; acessar campos por chave. Se a versão devolver o modelo Pydantic, usar atributo.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py -v`
Expected: FAIL (`ModuleNotFoundError: loopforge.graph`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/graph.py`:
```python
"""Grafo LangGraph: nós dos agentes, scoring e controle do loop."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from loopforge.agents.builder import AgentsBundle, build_agents
from loopforge.config import AppConfig
from loopforge.logging import get_logger
from loopforge.scoring.composite import score_composto
from loopforge.scoring.deterministic import score_deterministico
from loopforge.scoring.rubric import score_judge
from loopforge.state import IteracaoRegistro, LoopState

log = get_logger("graph")


def _ctx_texto(state: LoopState) -> str:
    """Serializa o contexto herdado para injetar nos prompts."""
    partes = [f"OBJETIVO: {state.objetivo}"]
    if state.contexto.docs:
        partes.append("DOCS: " + ", ".join(state.contexto.docs))
    if state.contexto.links:
        partes.append("LINKS: " + ", ".join(state.contexto.links))
    if state.contexto.best_practices_conteudo:
        partes.append("BEST PRACTICES (Asaas):\n" + state.contexto.best_practices_conteudo)
    return "\n".join(partes)


def decidir_loop(state: LoopState) -> str:
    """Decide o próximo passo do loop.

    Args:
        state: estado atual (usa score_final, iteracao, historico, config.loop).

    Returns:
        "aprovado" se score atingiu o mínimo; "para" se atingiu max_iter ou
        estagnou (no-progress); senão "reitera".
    """
    loop = state.config.loop
    if state.score_final >= loop.score_minimo:
        return "aprovado"
    if state.iteracao >= loop.max_iteracoes:
        return "para"

    paciencia = loop.no_progress_paciencia
    if len(state.historico) >= paciencia:
        ultimos = state.historico[-paciencia:]
        melhor_anterior = max(r.score_final for r in ultimos)
        if state.score_final <= melhor_anterior:
            return "para"
    return "reitera"


def build_builder(config: AppConfig, agents: AgentsBundle | None = None) -> StateGraph:
    """Monta o StateGraph (sem compilar).

    Args:
        config: configuração.
        agents: bundle de agentes; se None, criado de `config`.

    Returns:
        StateGraph pronto para compilar.
    """
    agents = agents or build_agents(config)

    async def discovery_node(state: LoopState) -> dict:
        if state.discovery_report:  # roda só na 1ª iteração
            return {}
        res = await agents.discovery.run(f"{_ctx_texto(state)}\n\nFaça o discovery.")
        log.info("discovery_ok", chars=len(res.output))
        return {"discovery_report": res.output}

    async def plan_node(state: LoopState) -> dict:
        prompt = (
            f"{_ctx_texto(state)}\n\nDISCOVERY:\n{state.discovery_report}\n\n"
            f"FEEDBACK DO JUDGE (iteração anterior):\n{state.judge_feedback or '—'}\n\n"
            "Produza/atualize a spec da skill."
        )
        res = await agents.plan.run(prompt)
        log.info("plan_ok", name=res.output.name)
        return {"plan": res.output}

    async def write_node(state: LoopState) -> dict:
        prompt = f"{_ctx_texto(state)}\n\nPLANO:\n{state.plan.model_dump_json()}\n\nEscreva a skill."
        res = await agents.write.run(prompt)
        log.info("write_ok", linhas=res.output.skill_md.count(chr(10)) + 1)
        return {"artifact": res.output}

    async def judge_node(state: LoopState) -> dict:
        prompt = (
            f"{_ctx_texto(state)}\n\nSKILL.md:\n{state.artifact.skill_md}\n\n"
            "Avalie a skill."
        )
        res = await agents.judge.run(prompt)
        verdict = res.output

        det, _ = score_deterministico(state.artifact, config.scoring.deterministico)
        bp_presente = state.contexto.best_practices_conteudo is not None
        jdg = score_judge(verdict, config.scoring.judge, bp_presente)
        final = score_composto(det, jdg, config.scoring.pesos)

        iteracao = state.iteracao + 1
        registro = IteracaoRegistro(
            iteracao=iteracao, score_final=final, score_det=det, score_judge=jdg
        )
        log.info("judge_ok", iteracao=iteracao, score_final=round(final, 4),
                 score_det=round(det, 4), score_judge=round(jdg, 4))
        novo_status = "aprovado" if final >= config.loop.score_minimo else state.status
        return {
            "verdict": verdict,
            "score_det": det,
            "score_judge": jdg,
            "score_final": final,
            "judge_feedback": verdict.feedback_acionavel,
            "iteracao": iteracao,
            "historico": [*state.historico, registro],
            "status": novo_status,
        }

    def _rotear(state: LoopState) -> str:
        decisao = decidir_loop(state)
        if decisao == "reitera":
            return "plan"
        # marca status terminal não-aprovado
        return decisao

    def finalizar_status(state: LoopState) -> dict:
        if state.status == "aprovado":
            return {}
        novo = "max_iter" if state.iteracao >= state.config.loop.max_iteracoes else "estagnado"
        return {"status": novo}

    builder = StateGraph(LoopState)
    builder.add_node("discovery", discovery_node)
    builder.add_node("plan", plan_node)
    builder.add_node("write", write_node)
    builder.add_node("judge", judge_node)
    builder.add_node("finalizar", finalizar_status)

    builder.add_edge(START, "discovery")
    builder.add_edge("discovery", "plan")
    builder.add_edge("plan", "write")
    builder.add_edge("write", "judge")
    builder.add_conditional_edges(
        "judge", _rotear, {"aprovado": "finalizar", "para": "finalizar", "plan": "plan"}
    )
    builder.add_edge("finalizar", END)
    return builder


def build_graph(config: AppConfig, agents: AgentsBundle | None = None, checkpointer=None):
    """Compila o grafo.

    Args:
        config: configuração.
        agents: bundle de agentes (opcional).
        checkpointer: checkpointer LangGraph (ex: SqliteSaver) ou None.

    Returns:
        Grafo compilado, invocável via `.ainvoke(LoopState(...))`.
    """
    return build_builder(config, agents).compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py -v`
Expected: PASS (5 testes). Ajustar acesso ao resultado (`final["status"]` vs `final.status`) conforme a versão do LangGraph.

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/graph.py tests/test_graph.py
git commit -m "feat: grafo LangGraph com nós, scoring no judge e controle de loop"
```

---

### Task 10: Persistência da skill no disco

**Files:**
- Create: `src/loopforge/persistence.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Consumes: `SkillArtifact` (state.py).
- Produces: `gravar_skill(artifact: SkillArtifact, output_dir: str | Path, nome: str) -> Path` — cria `<output_dir>/<nome>/SKILL.md` + arquivos referenciados (preservando subpastas); retorna o diretório da skill.

- [ ] **Step 1: Write the failing test**

`tests/test_persistence.py`:
```python
from loopforge.persistence import gravar_skill
from loopforge.state import SkillArtifact, SkillFile


def test_grava_skill_md_e_refs(tmp_path):
    art = SkillArtifact(
        skill_md="---\nname: x\ndescription: Use quando.\n---\n# X\n",
        arquivos=[SkillFile(caminho="references/guia.md", conteudo="conteudo")],
    )
    destino = gravar_skill(art, tmp_path, "minha-skill")
    assert (destino / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert (destino / "references" / "guia.md").read_text(encoding="utf-8") == "conteudo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_persistence.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/persistence.py`:
```python
"""Gravação da skill gerada no diretório de saída."""

from __future__ import annotations

import re
from pathlib import Path

from loopforge.state import SkillArtifact


def _slug(nome: str) -> str:
    """Normaliza um nome para diretório (minúsculo, hífens)."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_persistence.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/persistence.py tests/test_persistence.py
git commit -m "feat: gravação da skill (SKILL.md + refs) no output_dir"
```

---

### Task 11: CLI (`loopforge run` / `validate`) + runner

**Files:**
- Create: `src/loopforge/runner.py`
- Create: `src/loopforge/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config` (config.py), `build_contexto` (context.py), `build_graph` (graph.py), `gravar_skill` (persistence.py), `setup_logging` (logging.py), `SqliteSaver`.
- Produces:
  - `runner.run_loop(config_path, extra_docs, extra_links) -> LoopState` (async) — orquestra: load → contexto → grafo (com SqliteSaver em `.loopforge/runs/`) → grava skill se aprovado/parcial → retorna estado final.
  - `cli.app` (Typer) com comandos `run` e `validate`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import textwrap
from typer.testing import CliRunner

from loopforge.cli import app

runner = CliRunner()


def _cfg(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent("""
        agents:
          discovery: {model: google-gla:gemini-2.0-flash}
          plan:      {model: anthropic:claude-opus-4-8}
          write:     {model: anthropic:claude-opus-4-8}
          judge:     {model: google-gla:gemini-2.0-flash}
        skill: {objetivo: "Skill de teste"}
    """), encoding="utf-8")
    return p


def test_validate_ok(tmp_path):
    res = runner.invoke(app, ["validate", "--config", str(_cfg(tmp_path))])
    assert res.exit_code == 0
    assert "válid" in res.stdout.lower()


def test_validate_arquivo_inexistente():
    res = runner.invoke(app, ["validate", "--config", "/nao/existe.yaml"])
    assert res.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: loopforge.cli`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/runner.py`:
```python
"""Orquestração de alto nível: carrega config, roda o grafo, grava a skill."""

from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from loopforge.config import load_config
from loopforge.context import build_contexto
from loopforge.graph import build_graph
from loopforge.logging import get_logger
from loopforge.persistence import gravar_skill
from loopforge.state import Contexto, LoopState

log = get_logger("runner")


async def run_loop(
    config_path: str | Path,
    extra_docs: list[str] | None = None,
    extra_links: list[str] | None = None,
) -> LoopState:
    """Executa o loop completo a partir de um YAML.

    Args:
        config_path: caminho do YAML de configuração.
        extra_docs: docs adicionais da CLI.
        extra_links: links adicionais da CLI.

    Returns:
        Estado final do loop (status aprovado/max_iter/estagnado).
    """
    config = load_config(config_path)
    contexto: Contexto = build_contexto(config, extra_docs, extra_links)

    runs_dir = Path(".loopforge/runs")
    runs_dir.mkdir(parents=True, exist_ok=True)

    estado_inicial = LoopState(objetivo=config.skill.objetivo, contexto=contexto, config=config)

    with SqliteSaver.from_conn_string(str(runs_dir / "loopforge.sqlite")) as checkpointer:
        graph = build_graph(config, checkpointer=checkpointer)
        bruto = await graph.ainvoke(estado_inicial, config={"configurable": {"thread_id": "run"}})

    final = LoopState.model_validate(bruto)
    if final.artifact is not None:
        nome = final.plan.name if final.plan else "skill"
        destino = gravar_skill(final.artifact, config.skill.output_dir, nome)
        log.info("skill_gravada", destino=str(destino), status=final.status,
                 score_final=round(final.score_final, 4))
    return final
```

`src/loopforge/cli.py`:
```python
"""CLI do loopforge (Typer)."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from loopforge.config import load_config
from loopforge.logging import setup_logging
from loopforge.runner import run_loop

app = typer.Typer(help="Loop Engineer: gera SKILLs do Claude via loop multi-agente.")
console = Console()


@app.command()
def validate(config: str = typer.Option(..., "--config", "-c", help="Caminho do YAML.")) -> None:
    """Valida o YAML sem executar o loop."""
    load_config(config)  # levanta ValidationError/FileNotFoundError se inválido
    console.print(f"[green]Configuração válida:[/green] {config}")


@app.command()
def run(
    config: str = typer.Option(..., "--config", "-c", help="Caminho do YAML."),
    doc: list[str] = typer.Option(None, "--doc", help="Diretório de doc extra (repetível)."),
    link: list[str] = typer.Option(None, "--link", help="URL extra (repetível)."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Executa o loop e grava a SKILL resultante."""
    setup_logging(verbose=verbose)
    final = asyncio.run(run_loop(config, extra_docs=doc, extra_links=link))
    cor = "green" if final.status == "aprovado" else "yellow"
    console.print(
        f"[{cor}]Loop encerrado[/{cor}] — status={final.status} "
        f"score_final={final.score_final:.4f} iterações={final.iteracao}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add src/loopforge/runner.py src/loopforge/cli.py tests/test_cli.py
git commit -m "feat: CLI run/validate + runner com checkpointer SQLite"
```

---

### Task 12: LangGraph Studio (`langgraph.json`) + smoke E2E

**Files:**
- Create: `langgraph.json`
- Create: `src/loopforge/graph_app.py`
- Test: `tests/test_e2e.py`

**Interfaces:**
- Consumes: `build_graph` (graph.py), `load_config` (config.py).
- Produces: `graph_app.graph` — grafo compilado (sem checkpointer; o servidor do Studio injeta o seu) a partir de `config.yaml` (ou `config.example.yaml` como fallback), referenciado por `langgraph.json`.

- [ ] **Step 1: Write the failing test**

`tests/test_e2e.py`:
```python
import json
from pathlib import Path


def test_langgraph_json_aponta_para_o_grafo():
    cfg = json.loads(Path("langgraph.json").read_text(encoding="utf-8"))
    assert "loopforge" in json.dumps(cfg["graphs"])


def test_graph_app_expoe_grafo_compilado():
    from loopforge.graph_app import graph
    assert hasattr(graph, "ainvoke")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_e2e.py -v`
Expected: FAIL (`FileNotFoundError: langgraph.json` / `ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/loopforge/graph_app.py`:
```python
"""Ponto de entrada do grafo para o LangGraph Studio (`langgraph dev`)."""

from __future__ import annotations

from pathlib import Path

from loopforge.config import load_config
from loopforge.graph import build_graph

_config_path = "config.yaml" if Path("config.yaml").exists() else "config.example.yaml"
graph = build_graph(load_config(_config_path))
```

`langgraph.json`:
```json
{
  "dependencies": ["."],
  "graphs": {
    "loopforge": "./src/loopforge/graph_app.py:graph"
  },
  "env": ".env"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_e2e.py -v`
Expected: PASS (2 testes).

Verificação manual (opcional, exige chaves): `uv run langgraph dev` abre o Studio no browser e mostra o grafo `loopforge`.

- [ ] **Step 5: Commit**

```bash
git add langgraph.json src/loopforge/graph_app.py tests/test_e2e.py
git commit -m "feat: entrada do grafo p/ LangGraph Studio + smoke E2E"
```

---

### Task 13: Suíte completa + ajuste final de docs

**Files:**
- Modify: `README.md` (seção de troubleshooting de versões, se necessário)
- Test: toda a suíte

- [ ] **Step 1: Rodar a suíte inteira**

Run: `uv run pytest -v`
Expected: todos os testes PASS.

- [ ] **Step 2: Smoke do CLI**

Run: `uv run loopforge validate --config config.example.yaml`
Expected: "Configuração válida".

- [ ] **Step 3: Conferir cobertura do spec**

Conferir manualmente que cada item do spec (`docs/superpowers/specs/2026-06-23-loopforge-design.md`) tem tarefa correspondente. Anotar gaps, se houver, e abrir tarefa.

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "test: suíte verde + ajustes finais de documentação"
```

---

## Self-Review (preenchido pelo autor do plano)

**1. Spec coverage:** topologia 4 nós (Task 7, 9) ✓; métrica híbrida det+judge (Task 5, 6, 9) ✓; pesos configuráveis (Task 2) ✓; controle de loop 3 saídas (Task 9) ✓; best_practices injeção+score (Task 4, 6, 9) ✓; observabilidade logs (Task 8) + Studio (Task 12) ✓; memory spine SQLite (Task 11) ✓; CLI run/validate +docs/links (Task 11) ✓; testes com TestModel (Task 7, 9) ✓.

**2. Placeholder scan:** sem TBD/TODO; todo passo de código tem código. ✓

**3. Type consistency:** `SkillPlan/SkillArtifact/JudgeVerdict/LoopState` definidos na Task 3 e usados igual em 5/6/7/9/10/11; `AgentsBundle.{discovery,plan,write,judge}` consistente entre 7 e 9; `score_deterministico→tuple`, `score_judge→float`, `score_composto→float` usados conforme assinatura no `judge_node`. ✓

## Notas de risco conhecidas

- **APIs de versão:** `output_type` vs `result_type`, `.output` vs `.data` (PydanticAI), retorno de `ainvoke` dict vs modelo, `SqliteSaver.from_conn_string` como context manager (LangGraph) — verificar contra a versão instalada no início da Task 7/9/11 e ajustar.
- **`pytest.mark.anyio`:** depende de `anyio_mode`; se falhar, usar `asyncio_mode=auto` (já no pyproject) e `@pytest.mark.asyncio` com `pytest-asyncio`.
- **`CLAUDE.md`** tem schema YAML antigo (sem `write`/`scoring`/`best_practices`) — sync pendente, fora do escopo deste plano (aguardando OK do usuário).
