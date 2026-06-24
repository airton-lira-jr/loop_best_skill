# Loop Engineer — `loopforge`

Orquestração **multi-agente** (cada agente numa **LLM diferente**) que produz uma **SKILL do Claude**
de alta qualidade a partir de um objetivo declarado em YAML. Os agentes pesquisam, planejam, escrevem
e **julgam** a skill num **loop iterativo** que só termina quando a métrica de qualidade é atingida —
ou quando o teto de iterações / a estagnação são alcançados.

Construído com **PydanticAI** (agentes + tools + MCP), **LangGraph** (grafo + loop condicional),
**uv** (ambiente) e observabilidade dupla: **logs estruturados** + **LangGraph Studio**.

---

## Conceito: Loop Engineering

Em vez de um prompt manual, um *loop* roda os agentes iterativamente **contra um sinal real** — aqui,
um **score de qualidade da skill** — corrigindo-se a cada volta até passar no critério. O loop tem
**saída garantida** por três vias independentes (score atingido, teto de iterações, ou estagnação).

```
                    ┌──── contexto herdado (docs, links, best_practices SKILL) ────┐
                    ▼                                                               │
  objetivo ─▶ [Discovery] ─▶ [Plan] ─▶ gate? ─sim─▶ [Write] ─▶ [Judge] ─▶ decide?
  (YAML)      (Gemini)      (Claude)    │            (Claude)    (Gemini)     │
                                        │não                                  ├─ score≥min ─▶ FIM (grava skill)
                                        └── volta p/ Plan ◀── reprovado & ────┤
                                            (com feedback)   iter<max          └─ iter≥max OU no-progress ─▶ FIM (parcial)
```

| Nó | Papel | LLM (default) |
|----|-------|---------------|
| **Discovery** | Propõe **N abordagens** candidatas pro objetivo (com prós/contras/adequação) e **recomenda a melhor**. Roda 1x. | `google-gla:gemini-2.0-flash` |
| **Plan** | **Escolhe a melhor abordagem** e a converte numa **spec da skill**. É o nó que **itera** no loop. | `anthropic:claude-opus-4-8` |
| **Write** | Escreve `SKILL.md` + arquivos referenciados. | `anthropic:claude-opus-4-8` |
| **Judge** | Avalia a skill e produz o score. **LLM diferente do Write** (anti-viés). | `anthropic:claude-sonnet-4.6` |

Os agentes "conversam" via **estado compartilhado** do grafo: o Discovery levanta opções, o Plan decide
o melhor caminho, e o feedback do Judge volta pro Plan na iteração seguinte. **Quem define a melhor
abordagem pro objetivo é a interação entre os agentes**, não parâmetros manuais.

---

## Instalação

```bash
uv sync                 # resolve dependências do pyproject.toml
cp config.example.yaml config.yaml
# exporte as chaves dos providers que você usa:
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...     # (ou GOOGLE_API_KEY, conforme o provider)
```

## Uso

```bash
# Rodar o loop lendo ./config.yaml por padrão (forma mais curta):
uv run loopforge

# Equivalente explícito (--config default = config.yaml):
uv run loopforge run --config config.yaml

# Validar o YAML sem executar o loop:
uv run loopforge validate            # usa ./config.yaml
uv run loopforge validate --config outro.yaml

# Injetar contexto extra (estende contexto.docs / contexto.links do YAML):
uv run loopforge run --doc ./docs --link https://exemplo.com

# Monitorar o grafo ao vivo no browser (LangGraph Studio):
uv run langgraph dev
```

> `uv run loopforge` sem subcomando roda o loop lendo `config.yaml` do diretório atual. O `--config`
> é opcional (default `config.yaml`); informe-o só para apontar para outro arquivo.

---

## Configuração YAML

Dois exemplos: [`config.example.yaml`](./config.example.yaml) é o **mínimo** (só o essencial;
`loop` e `scoring` usam defaults) e [`config.full.example.yaml`](./config.full.example.yaml) mostra
**todos** os campos comentados. Chaves canônicas:

- `agents.{discovery,plan,write,judge}.model` — LLM de cada nó (formato `provider:modelo`).
- `skill.objetivo` — o alvo do loop. Aceita **texto literal OU um path**: se for um arquivo, lê o
  conteúdo; se for um diretório, concatena os `.md` dentro dele. Use arquivo para objetivos longos
  (evita a dor de quebra de linha no YAML).
- `skill.output_dir` — onde a SKILL final é gravada.
- `skill.best_practices` — **opcional**. Path para uma SKILL com as regras da Asaas. É **injetada como
  contexto herdado** em todos os agentes **e** pontuada pelo Judge (dimensão `aderencia_best_practices`).
  `null`/omitido (ou arquivo ausente) ⇒ a dimensão é dropada e os pesos do Judge são renormalizados.
- `loop.*` — **opcional** (defaults: `max_iteracoes=6`, `score_minimo=0.8`, `no_progress_paciencia=2`).
- `scoring.*` — **opcional**; pesos da métrica com defaults sensatos (detalhado abaixo). Só mexa se
  quiser recalibrar.
- `contexto.{docs,links}` — fontes de referência (também via flags `--doc`/`--link`). **O conteúdo é
  lido/baixado e injetado nos agentes** — detalhe na seção abaixo.
- `mcp.{config_path,agentes}` — **opcional**. Servidores MCP que os agentes podem chamar ao vivo
  (Confluence, Jira, etc.) — detalhe na seção "MCP" abaixo.

---

## Como passar objetivo, referências e onde a skill é gravada

Esta é a parte que liga o **seu material** ("o monte de coisa pra atingir o objetivo") aos agentes.

### 1. O objetivo

No YAML, em `skill.objetivo`. Descreva **a skill que você quer**, não "construa o sistema X" —
o loopforge gera uma **SKILL do Claude** (um `SKILL.md` + arquivos de referência), não um serviço.

O campo aceita **texto direto** ou um **path** (arquivo `.md` ou diretório de `.md`). Para objetivos
longos, prefira o arquivo — sem quebra de linha feia no YAML:

```yaml
skill:
  objetivo: "Skill que revisa PRs de Python procurando bugs de concorrência"  # texto direto
  # objetivo: "./objetivo/skill.md"   # ou um arquivo
  # objetivo: "./objetivo"            # ou um diretório de .md (concatenados)
```

### 2. Arquivos de referência (`docs`) e links

Você define em **dois lugares** (os dois se somam):

- No YAML, em `contexto.docs` / `contexto.links`.
- Na CLI, com `--doc <path>` / `--link <url>` (repetíveis) — **estendem** o YAML.

```yaml
contexto:
  docs:  ["./docs/arquitetura", "./referencias/guia.md"]   # arquivo OU diretório
  links: ["https://docs.python.org/3/library/asyncio.html"]
```
```bash
uv run loopforge run --config config.yaml \
  --doc ./docs/extra --doc ./padroes.md \
  --link https://exemplo.com/guia
```

**O que de fato acontece com cada um:**

| Entrada | O que é injetado nos agentes |
|---|---|
| `contexto.docs` (arquivo) | O **conteúdo do arquivo** é lido (UTF-8) e injetado. |
| `contexto.docs` (diretório) | Percorrido **recursivamente**; lê só arquivos de texto (`.md`, `.txt`, `.py`, `.yaml`, ...). Ignora binários, ocultos e arquivos > 200 KB. |
| `contexto.links` | O **corpo da URL** é baixado via HTTP e injetado. Link que falhar (rede/404) é ignorado — o loop segue sem ele. |
| `skill.best_practices` | O **conteúdo** da SKILL apontada é injetado **e** pontuado pelo Judge (`aderencia_best_practices`). |

Ou seja: para um arquivo de referência **influenciar de verdade** o Discovery/Plan, basta colocá-lo em
`contexto.docs` (ou passar `--doc`). O conteúdo entra no prompt de todos os 4 agentes.

### 3. Onde a skill final é gravada

No diretório `skill.output_dir` (default `./skills`), dentro de uma subpasta com o nome da skill em
slug. Ex.: `./skills/pr-review/SKILL.md` + os arquivos referenciados. Os runs (memory spine / SQLite)
ficam em `.loopforge/runs/` (ignorado pelo git).

---

## MCP — tools que os agentes usam ao vivo (Confluence, Jira, ...)

Diferente de `contexto.links` (que baixa um snapshot estático), o MCP dá aos agentes **tools que eles
chamam sozinhos durante a execução**, quando julgam necessário. Útil quando o material muda ou exige
consulta dinâmica (buscar uma página do Confluence, ler um ticket do Jira, etc.).

### Como ligar

1. Tenha um JSON no formato `mcpServers` (o **mesmo** do Claude Desktop / Cursor / Claude Code). Ex.
   `.mcp.json`:

```json
{
  "mcpServers": {
    "confluence": {
      "command": "npx", "args": ["-y", "mcp-confluence"],
      "env": {"CONFLUENCE_TOKEN": "${CONFLUENCE_TOKEN}"}
    },
    "jira": { "command": "npx", "args": ["-y", "mcp-jira"] }
  }
}
```

2. Aponte o YAML para ele:

```yaml
mcp:
  config_path: "./.mcp.json"
  agentes: [discovery, plan, write]   # quais nós ganham as tools (Judge fora por padrão)
```

### Como funciona

- Cada server vira uma toolset **prefixada pelo nome** (`confluence_*`, `jira_*`) — sem colisão entre
  servers.
- Variáveis de ambiente no JSON: `${VAR}` (obrigatória) ou `${VAR:-default}`.
- Os agentes em `mcp.agentes` recebem as tools e **decidem em runtime** quando chamá-las. O **Judge
  fica de fora por padrão** (avalia a skill sem viés de ferramenta).
- As conexões MCP são abertas no início do run e fechadas no fim (gerenciadas pelo runner).
- Sem `mcp.config_path`, nada muda — nenhum agente recebe tools.

> Reaproveite os servers que você **já tem habilitados** no Claude Code: aponte `config_path` para o
> mesmo JSON de `mcpServers`.

---

## A métrica de qualidade (pesos e o que significam)

A decisão de **aprovar ou repetir** o loop vem de um **score composto híbrido** entre 0.0 e 1.0:

```
score_final = pesos.deterministico · score_det  +  pesos.judge · score_judge
            =        0.30          · score_det  +       0.70    · score_judge   (defaults)
```

Por que híbrido? Métrica matemática pura é arbitrária; bibliotecas NLP (BLEU/ROUGE) medem similaridade
contra uma referência — e **não existe skill de referência**. A combinação dá o melhor dos dois mundos:
a camada determinística é **reprodutível e quase grátis** e barra erros óbvios (frontmatter quebrado);
a camada LLM-judge captura **qualidade semântica** (a skill realmente cumpre o objetivo?). O desenho
espelha a recomendação oficial da Anthropic de medir *invocação* + *qualidade do output* separadamente.

### Camada determinística — `scoring.deterministico` (peso 0.30)

Checks programáticos; cada um produz `0..1`. `score_det` = soma ponderada (pesos somam 1.0):

| Check | Peso | Significado | Como pontua |
|-------|------|-------------|-------------|
| `frontmatter_valido` | 0.25 | YAML do frontmatter parseia e tem `name` + `description` | 0 ou 1 |
| `description_tem_trigger` | 0.25 | `description` tem gatilho de uso ("Use when…/Use quando…") — **causa #1 de skill não carregar** | 0 ou 1 |
| `dentro_budget` | 0.20 | `SKILL.md` dentro do teto de linhas (concisão) | `1.0` se ≤ budget; senão `max(0, 1 − (linhas − budget) / budget)` |
| `refs_existem` | 0.15 | Arquivos referenciados existem (progressive disclosure intacto) | fração dos refs que existem |
| `markdown_valido` | 0.15 | Markdown bem-formado | 0 ou 1 |

`budget_linhas` (default `500`) é o teto usado pelo check `dentro_budget`.

### Camada LLM-judge — `scoring.judge` (peso 0.70)

O agente **Judge** devolve nota `0..1` por dimensão (structured output tipado via PydanticAI).
`score_judge` = média ponderada (pesos somam 1.0):

| Dimensão | Peso | Significado |
|----------|------|-------------|
| `alinhamento_objetivo` | 0.30 | A skill cumpre o `skill.objetivo`? |
| `discoverability` | 0.20 | Qualidade da description/triggers — Claude carrega na hora certa? |
| `concisao_clareza` | 0.15 | Regra+porquê em vez de imperativo; sem redundância |
| `completude` | 0.20 | Cobre o objetivo de ponta a ponta? |
| `aderencia_best_practices` | 0.15 | Segue a SKILL `skill.best_practices` da Asaas? |

### Exemplo numérico

Suponha uma skill gerada com:

**Determinístico:** frontmatter ok (`1.0`), trigger presente (`1.0`), `SKILL.md` com 620 linhas
(budget 500 → `1 − 120/500 = 0.76`), 2 de 3 refs existem (`0.667`), markdown ok (`1.0`).

```
score_det = 0.25·1.0 + 0.25·1.0 + 0.20·0.76 + 0.15·0.667 + 0.15·1.0
          = 0.25 + 0.25 + 0.152 + 0.100 + 0.15
          = 0.902
```

**Judge:** alinhamento `0.90`, discoverability `0.80`, concisão `0.70`, completude `0.85`,
aderência `0.90`.

```
score_judge = 0.30·0.90 + 0.20·0.80 + 0.15·0.70 + 0.20·0.85 + 0.15·0.90
            = 0.270 + 0.160 + 0.105 + 0.170 + 0.135
            = 0.840
```

**Composto:**

```
score_final = 0.30·0.902 + 0.70·0.840 = 0.2706 + 0.588 = 0.8586 ≈ 0.86
```

Com `loop.score_minimo: 0.8` → `0.86 ≥ 0.8` → **aprovado**, loop encerra e grava a skill.
Se fosse `0.74`, voltaria pro Plan com o feedback do Judge (até `max_iteracoes` ou estagnação).

> Todos os pesos e o `budget_linhas` são **configuráveis** no YAML — ajuste o rigor sem tocar no código.

---

## Saída do loop (3 condições, qualquer uma encerra)

| Condição | Resultado |
|----------|-----------|
| `score_final ≥ loop.score_minimo` | **Aprovado** — grava a skill em `skill.output_dir` |
| `iteracao ≥ loop.max_iteracoes` | **Para** — grava a skill **parcial** + relatório |
| score não melhora por `loop.no_progress_paciencia` iterações | **Para** (estagnação) — evita queimar tokens |

---

## Observabilidade

- **Logs estruturados** (structlog + rich) — cada transição de nó, score por dimensão e decisão de
  loop no terminal. Sempre ligado.
- **LangGraph Studio** — `uv run langgraph dev` sobe um servidor in-memory e abre o Studio no browser:
  grafo ao vivo, inspeção de estado e *time-travel* por iteração. O estado é persistido via checkpointer
  SQLite (`.loopforge/runs/`), que também serve de *memory spine* (sobrevive entre runs / permite resume).

---

## Desenvolvimento

```bash
uv run pytest                      # suíte completa
uv run pytest <caminho>::<teste>   # um único teste
uv add <pacote> / uv remove <pacote>
```

Os agentes são testados sem chamar API real via **`TestModel`/`FunctionModel`** do PydanticAI.

## Referências

- [Agent Skills — Anthropic Engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Skill authoring best practices — Claude Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Agentic Loops: From ReAct to Loop Engineering (2026)](https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/)
