# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Status do repositório:** implementado (tasks 1-13 do plano em `docs/superpowers/plans/`). A CLI
> `loopforge run`/`validate`, o grafo LangGraph de 4 nós, o scoring híbrido e a suíte de testes já
> existem. Mantenha este arquivo sincronizado com a estrutura real ao evoluir o código.

## Propósito

**Loop Engineer** — um conceito de orquestração multi-agente onde cada agente de IA roda em uma
**LLM diferente** e desempenha um papel especializado dentro de um loop iterativo de refinamento.
O objetivo final do loop é produzir uma **SKILL** (artefato de implantação) que atenda a um objetivo
definido pelo usuário.

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
  recomendada + justificativa) e recomenda a melhor. Roda só na 1ª iteração.
- **Plan Agent** — escolhe a melhor abordagem e elabora a spec da SKILL (`SkillPlan`). É o nó que itera,
  incorporando o feedback do Judge.
- **Write Agent** — escreve o `SKILL.md` (frontmatter + corpo) e os arquivos referenciados
  (`SkillArtifact`) a partir da spec.
- **Judge Agent** — avalia o artefato e produz um veredito estruturado (`JudgeVerdict`): nota 0..1 por
  dimensão + feedback acionável. É essa métrica que alimenta a decisão de loop.
- O loop **reitera** enquanto o score ficar abaixo do `score_minimo`, respeitando o teto
  `max_iteracoes` e a paciência anti-estagnação (`no_progress_paciencia`).

## Stack

| Camada | Tecnologia | Papel |
|--------|-----------|-------|
| Gerenciador de pacotes | **uv** | Ambiente, dependências e execução (`uv sync`, `uv run`) |
| Agentes de IA | **PydanticAI** | Definição de cada agente, *tools* e integração **MCP** (todo o harness possível) |
| Orquestração | **LangGraph** | Grafo Discovery → Plan → Write → Judge, com aresta de loop condicional e checkpointer SQLite (memory spine) |
| Interface | **CLI `loopforge`** (Typer; documentada no `README.md`) | Comandos `run`/`validate` e recursos extras (links, diretórios de docs) como contexto |
| Configuração | **YAML** | Arquivo lido antes da execução (LLM de cada agente, objetivo da SKILL, loop e pesos do scoring) |
| Observabilidade | Logs estruturados (**structlog + rich**) + **LangGraph Studio** (`langgraph dev`) | Acompanhar a execução em tempo real |

## Arquivo de configuração YAML

A aplicação **lê o YAML antes da execução**. Campos obrigatórios:

1. **LLM de cada agente** — `discovery`, `plan`, `write`, `judge` (cada um pode ser uma LLM distinta).
2. **Objetivo da SKILL** — o alvo que o loop deve atingir.

Os demais campos têm defaults (loop e pesos do scoring). Esquema oficial (formato de `model` segue o
padrão PydanticAI `provider:modelo`). Veja `config.example.yaml` para a versão anotada completa:

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
  config_path: null         # JSON formato `mcpServers` (Claude Desktop/Cursor/Claude Code)
  agentes: [discovery, plan, write]  # nós que recebem as tools (Judge fora por padrão)
```

> **Anti-viés (default):** `agents.judge.model` deve usar um provider **≠** `agents.write.model`,
> para o avaliador não ser cúmplice de quem escreveu. Os 4 nós do grafo são `discovery`, `plan`,
> `write`, `judge`.

Chaves canônicas: `agents.{discovery,plan,write,judge}.model`, `skill.objetivo`,
`skill.output_dir`, `skill.best_practices` (opcional), `loop.max_iteracoes`, `loop.score_minimo`,
`loop.no_progress_paciencia`, `scoring.pesos.{deterministico,judge}`,
`scoring.deterministico.*`, `scoring.judge.*`, `contexto.docs`, `contexto.links`,
`mcp.config_path` (opcional), `mcp.agentes`.

> A validação de pesos é estrita: `scoring.pesos`, `scoring.deterministico` (5 checks) e
> `scoring.judge` (5 dimensões) **cada grupo deve somar 1.0**, senão o load levanta `ValidationError`.

> Cada agente usa uma LLM **diferente** por design — isso é central ao conceito. Não force todos
> os agentes para o mesmo provider/modelo sem instrução explícita.

## Conceitos centrais (ao implementar, respeitar)

- **Papéis isolados por LLM** — Discovery, Plan, Write e Judge são agentes PydanticAI separados, cada
  um com seu modelo configurado via YAML. Evite acoplar lógica entre eles fora do grafo.
- **Loop com saída garantida** — `decidir_loop` (em `graph.py`) checa **score** (`loop.score_minimo`),
  **teto de iterações** (`loop.max_iteracoes`) **e** estagnação (`loop.no_progress_paciencia`). Sai do
  loop SEMPRE que qualquer um for atingido: `aprovado`, `max_iter` ou `estagnado`.
- **Métrica híbrida** — score composto: `score_final = pesos.deterministico * det + pesos.judge * jdg`.
  A camada determinística roda checks programáticos sobre o `SkillArtifact`; a camada judge é a rubrica
  do Judge (saída tipada `JudgeVerdict`). Sem `best_practices`, a dimensão `aderencia_best_practices` é
  dropada e os pesos do judge são renormalizados.
- **best_practices como contexto herdado (opcional)** — quando `skill.best_practices` aponta p/ uma
  SKILL, seu conteúdo é injetado nos prompts de todos os agentes **e** pontuado pelo Judge. Ausente
  (null/omitido/arquivo inexistente) ⇒ a dimensão `aderencia_best_practices` é dropada e renormalizada.
- **MCP autônomo (opcional)** — com `mcp.config_path` (JSON `mcpServers` padrão), os agentes em
  `mcp.agentes` recebem toolsets MCP via `load_mcp_toolsets` e as chamam em runtime quando precisam
  (Confluence/Jira/etc.). O runner abre/fecha as conexões em volta do `ainvoke` (`async with agent`).
  Judge fica sem tools por padrão. Carga é preguiçosa (não conecta em teste).
- **Contexto incremental via CLI** — links e diretórios de doc passados na CLI (`--doc`/`--link`)
  estendem `contexto.docs`/`contexto.links` do YAML. Trate-os como entrada, não hardcode.
- **Observabilidade dupla** — toda execução emite (a) logs estruturados (structlog/rich) e (b) é
  inspecionável no LangGraph Studio (`langgraph.json` → `graph_app.py:graph`). O checkpointer SQLite em
  `.loopforge/runs/` serve de memory spine e time-travel. Não remova/silencie instrumentação ao refatorar.
- **Agentes nunca chamam API real em teste** — usar `TestModel`/`FunctionModel` do PydanticAI via
  `agent.override(model=...)`.

## Comandos

> A CLI `loopforge` é **documentada no `README.md`** (fonte de verdade dos comandos e flags).
> O grafo p/ o Studio fica em `langgraph.json`.

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

Ao mudar comandos ou flags, **atualize esta seção e o `README.md` juntos** — eles não devem divergir.
