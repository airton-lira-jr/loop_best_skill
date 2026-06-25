# CLAUDE.md

Guia Claude Code (claude.ai/code) para trabalho neste repo.

> **Status do repositório:** implementado (tasks 1-13 do plano em `docs/superpowers/plans/`). CLI
> `loopforge run`/`validate`, grafo LangGraph 4 nós, scoring híbrido, suíte de testes já
> existem. Mantenha arquivo sincronizado com estrutura real ao evoluir código.

## Propósito

**Loop Engineer** — orquestração multi-agente onde cada agente IA roda em
**LLM diferente**, papel especializado dentro de loop iterativo de refinamento.
Objetivo do loop: produzir **SKILL** (artefato de implantação) que atenda objetivo
do usuário.

### O ciclo (loop)

```
Objetivo do usuário (YAML)
        │
        ▼
┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐
│ DISCOVERY │──▶│   PLAN    │──▶│   WRITE   │──▶│   JUDGE   │
│ (LLM A)   │   │ (LLM B)   │   │ (LLM C)   │   │ (LLM D)   │
│ levanta   │   │ elabora a │   │ escreve a │   │ pontua a  │
│ soluções  │   │ spec da   │   │ SKILL.md  │   │ SKILL por │
│ e techs   │   │ SKILL     │   │ + refs    │   │ rubrica   │
└───────────┘   └───────────┘   └───────────┘   └─────┬─────┘
        ▲                                              │
        │      reprovado (score < score_minimo)        │
        │      e iter < max_iteracoes (com feedback)   │
        └──────────────── reitera ─────────────────────┤
                                                        │ aprovado / para
                                                        ▼
                                                  SKILL final
```

- **Discovery Agent** — propõe N abordagens candidatas (`DiscoveryReport` com `Abordagem[]` +
  recomendada + justificativa), recomenda melhor. Roda só na 1ª iteração.
- **Plan Agent** — escolhe melhor abordagem, elabora spec da SKILL (`SkillPlan`). Nó que itera,
  incorpora feedback do Judge.
- **Write Agent** — escreve `SKILL.md` (frontmatter + corpo) e arquivos referenciados
  (`SkillArtifact`) a partir da spec.
- **Judge Agent** — avalia artefato, produz veredito estruturado (`JudgeVerdict`): nota 0..1 por
  dimensão + feedback acionável. Essa métrica alimenta decisão de loop.
- Loop **reitera** enquanto score abaixo do `score_minimo`, respeita teto
  `max_iteracoes` e paciência anti-estagnação (`no_progress_paciencia`).

## Stack

| Camada | Tecnologia | Papel |
|--------|-----------|-------|
| Gerenciador de pacotes | **uv** | Ambiente, dependências, execução (`uv sync`, `uv run`) |
| Agentes de IA | **PydanticAI** | Define cada agente, *tools*, integração **MCP** (todo harness possível) |
| Orquestração | **LangGraph** | Grafo Discovery → Plan → Write → Judge, aresta de loop condicional + checkpointer SQLite (memory spine) |
| Interface | **CLI `loopforge`** (Typer; documentada no `README.md`) | Comandos `run`/`validate` + recursos extras (links, diretórios de docs) como contexto |
| Configuração | **YAML** | Arquivo lido antes da execução (LLM de cada agente, objetivo da SKILL, loop, pesos do scoring) |
| Observabilidade | Logs estruturados (**structlog + rich**) + **LangGraph Studio** (`langgraph dev`) | Acompanha execução em tempo real |

## Arquivo de configuração YAML

Aplicação **lê YAML antes da execução**. Campos obrigatórios:

1. **LLM de cada agente** — `discovery`, `plan`, `write`, `judge` (cada um pode ser LLM distinta).
2. **Objetivo da SKILL** — alvo que loop deve atingir.

Demais campos têm defaults (loop e pesos do scoring). Esquema oficial (formato de `model` segue
padrão PydanticAI `provider:modelo`). Veja `config.example.yaml` para versão anotada completa:

```yaml
agents:
  discovery:
    model: google-gla:gemini-2.0-flash    # LLM do agente de Discovery
  plan:
    model: anthropic:claude-opus-4-8       # LLM do agente de Plan
  write:
    model: anthropic:claude-opus-4-8       # LLM do agente de Write
  judge:
    model: google-gla:gemini-2.0-flash     # LLM do agente de Validação/Judge

skill:
  objetivo: "<texto OU path .md/diretório>" # texto literal ou path (arquivo/dir de .md) → lido
  output_dir: "./skills"                  # onde a SKILL final é gravada
  best_practices: null                    # opcional; path p/ uma SKILL com regras Asaas

loop:
  max_iteracoes: 6          # teto do loop (anti loop-infinito)
  score_minimo: 0.8         # threshold de qualidade p/ aprovar a SKILL (0.0–1.0)
  no_progress_paciencia: 2  # iterações sem melhora do melhor score antes de parar

scoring:                    # pesos opcionais (cada grupo deve somar 1.0)
  pesos:
    deterministico: 0.30    # peso da camada de checks programáticos
    judge: 0.70             # peso da camada LLM-as-judge
  deterministico:           # 5 checks (somam 1.0) + budget de linhas
    frontmatter_valido: 0.25
    description_tem_trigger: 0.25
    dentro_budget: 0.20
    refs_existem: 0.15
    markdown_valido: 0.15
    budget_linhas: 500
  judge:                    # 5 dimensões da rubrica (somam 1.0)
    alinhamento_objetivo: 0.30
    discoverability: 0.20
    concisao_clareza: 0.15
    completude: 0.20
    aderencia_best_practices: 0.15

contexto:                   # opcional; também passável via flags da CLI
  docs: []                  # arquivos/diretórios; o conteúdo é lido e injetado
  links: []                 # URLs; o corpo é baixado (httpx) e injetado

mcp:                        # opcional; tools MCP que os agentes chamam ao vivo
  auto: true                # herda os MCP locais da sessão do Claude Code (default)
  incluir: null             # allowlist de servers (null = todos); excluir = denylist
  excluir: []
  config_path: null         # override: JSON formato `mcpServers` (desliga o auto)
  agentes: [discovery, plan, write]  # nós que recebem as tools (Judge fora por padrão)
```

> **Anti-viés (default):** `agents.judge.model` deve usar provider **≠** `agents.write.model`,
> p/ avaliador não ser cúmplice de quem escreveu. 4 nós do grafo: `discovery`, `plan`,
> `write`, `judge`.

> **Chaves de API:** NÃO vão no YAML. PydanticAI lê do ambiente
> (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `OPENAI_API_KEY`). `run_loop` carrega `.env`
> via `loopforge.env.carregar_env` (override=False; shell vence). São API keys (cobrança por token),
> não a assinatura Pro/Max.

Chaves canônicas: `agents.{discovery,plan,write,judge}.model`, `skill.objetivo`,
`skill.output_dir`, `skill.best_practices` (opcional), `loop.max_iteracoes`, `loop.score_minimo`,
`loop.no_progress_paciencia`, `scoring.pesos.{deterministico,judge}`,
`scoring.deterministico.*`, `scoring.judge.*`, `contexto.docs`, `contexto.links`,
`mcp.auto` (default true), `mcp.config_path` (override opcional), `mcp.agentes`.

> Validação de pesos estrita: `scoring.pesos`, `scoring.deterministico` (5 checks),
> `scoring.judge` (5 dimensões) — **cada grupo deve somar 1.0**, senão load levanta `ValidationError`.

> Cada agente usa LLM **diferente** por design — central ao conceito. Não force todos
> agentes p/ mesmo provider/modelo sem instrução explícita.

## Conceitos centrais (ao implementar, respeitar)

- **Papéis isolados por LLM** — Discovery, Plan, Write, Judge são agentes PydanticAI separados, cada
  um com modelo configurado via YAML. Evite acoplar lógica entre eles fora do grafo.
- **Loop com saída garantida** — `decidir_loop` (em `graph.py`) checa **score** (`loop.score_minimo`),
  **teto de iterações** (`loop.max_iteracoes`) **e** estagnação (`loop.no_progress_paciencia`). Sai do
  loop SEMPRE que qualquer um for atingido: `aprovado`, `max_iter` ou `estagnado`.
- **Métrica híbrida** — score composto: `score_final = pesos.deterministico * det + pesos.judge * jdg`.
  Camada determinística roda checks programáticos sobre `SkillArtifact`; camada judge é rubrica
  do Judge (saída tipada `JudgeVerdict`). Sem `best_practices`, dimensão `aderencia_best_practices`
  dropa, pesos do judge renormalizam.
- **best_practices como contexto herdado (opcional)** — quando `skill.best_practices` aponta p/
  SKILL, conteúdo injeta nos prompts de todos agentes **e** Judge pontua. Ausente
  (null/omitido/arquivo inexistente) ⇒ dimensão `aderencia_best_practices` dropa, renormaliza.
- **MCP autônomo (opcional, auto por padrão)** — `mcp_discovery.preparar_mcp_config` (async): descobre
  servers MCP **locais** da sessão (`descobrir_mcp_servers`: mescla `~/.claude.json` global+projeto e
  `.mcp.json`), aplica `incluir`/`excluir`, faz **probe** de cada um (conecta isolado; os que falham são
  **descartados** — server quebrado nunca derruba o loop), grava JSON temporário (0600) só com saudáveis,
  injeta em `mcp.config_path`. `mcp.config_path` explícito é override, desliga auto. Agentes em
  `mcp.agentes` recebem toolsets via `load_mcp_toolsets`, chamam em runtime; runner abre/fecha conexões
  em volta do `ainvoke` (`async with agent`). Judge sem tools por padrão. Connectors do claude.ai
  (OAuth) NÃO herdáveis — só servers locais.
- **Contexto incremental via CLI** — links e diretórios de doc passados na CLI (`--doc`/`--link`)
  estendem `contexto.docs`/`contexto.links` do YAML. Trate como entrada, não hardcode.
- **Observabilidade dupla** — toda execução emite (a) logs estruturados (structlog/rich) e (b)
  inspecionável no LangGraph Studio (`langgraph.json` → `graph_app.py:graph`). Checkpointer SQLite em
  `.loopforge/runs/` serve de memory spine + time-travel. Não remova/silencie instrumentação ao refatorar.
- **Agentes nunca chamam API real em teste** — usar `TestModel`/`FunctionModel` do PydanticAI via
  `agent.override(model=...)`.

## Comandos

> CLI `loopforge` **documentada no `README.md`** (fonte de verdade dos comandos e flags).
> Grafo p/ Studio fica em `langgraph.json`.

```bash
# Setup do ambiente (uv lê o pyproject.toml e resolve as dependências):
uv sync

# Rodar a aplicação a partir de uma config YAML:
uv run loopforge run --config config.yaml

# Passar recursos adicionais de contexto (sobrepõem/estendem contexto.docs e contexto.links):
uv run loopforge run --config config.yaml --doc ./docs --link https://exemplo.com

# Validar o YAML sem executar o loop:
uv run loopforge validate --config config.yaml

# Testes:
uv run pytest                      # suíte completa
uv run pytest <caminho>::<teste>   # um único teste

# Abrir o LangGraph Studio (visualização do grafo; exige chaves de API):
uv run langgraph dev

# Adicionar/remover dependências:
uv add <pacote>
uv remove <pacote>
```

Ao mudar comandos ou flags, **atualize esta seção e o `README.md` juntos** — não devem divergir.