# Loop Engineer — `loopforge`

Orquestração **multi-agente** (cada agente numa **LLM diferente**) que produz uma **SKILL do Claude**
de alta qualidade a partir de um objetivo declarado em YAML. Os agentes pesquisam, planejam, escrevem
e **julgam** a skill num **loop iterativo** que só termina quando a métrica de qualidade é atingida —
ou quando o teto de iterações / a estagnação são alcançados.

Construído com **PydanticAI** (agentes + tools + MCP + **web search**), **LangGraph** (grafo + loop
condicional), **uv** (ambiente) e observabilidade dupla: **logs estruturados** + **LangGraph Studio**.

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
cp .env.example .env     # preencha as chaves dos providers que você usa
```

### Chaves de API (autenticação dos modelos)

As chaves **não vão no YAML** — o YAML só escolhe o modelo (`provider:modelo`). A autenticação é por
variável de ambiente, lida pelo PydanticAI. O loopforge **carrega o `.env` automaticamente** ao rodar
(`.env` está no `.gitignore`); variáveis já exportadas no shell têm precedência.

| Provider (no YAML) | Variável | Onde obter |
|---|---|---|
| `openrouter:...` (inclui `:free`) | `OPENROUTER_API_KEY` | openrouter.ai/keys |
| `nvidia:...` (API gratuita) | `NVIDIA_API_KEY` | build.nvidia.com |
| `anthropic:...` | `ANTHROPIC_API_KEY` | console.anthropic.com |
| `google-gla:...` | `GEMINI_API_KEY` (ou `GOOGLE_API_KEY`) | aistudio.google.com/apikey |
| `openai:...` | `OPENAI_API_KEY` | platform.openai.com/api-keys |

**NVIDIA NIM (API gratuita).** Formato: `model: nvidia:<id>`, ex. `nvidia:google/gemma-4-31b-it`. O `<id>`
é o slug do catálogo em build.nvidia.com/models (copie da URL da página do modelo). O endpoint é
OpenAI-compatible (`integrate.api.nvidia.com`); o loopforge resolve o prefixo `nvidia:` e usa a
`NVIDIA_API_KEY` (chave `nvapi-...`). Uma só chave serve para todos os agentes.

**OpenRouter (modelos gratuitos).** Formato: `model: openrouter:<id>`, ex. `openrouter:qwen/qwen3-coder:free`
(o `:free` faz parte do id; veja os ids atuais em openrouter.ai/models). Uma só `OPENROUTER_API_KEY`
serve para todos os agentes. Dois cuidados com modelos `:free`:
- **Saída tipada:** os agentes usam *structured output* (via tool-calling). Escolha modelos free que
  suportem function-calling/tools, senão a saída tipada falha. Modelos de raciocínio puro costumam não servir.
- **Rate limit:** os `:free` têm limites agressivos (req/min e por dia); um loop com várias iterações
  pode esbarrar. Reduza `loop.max_iteracoes` se necessário.

> Estas são **API keys** (cobrança por token), **não** a assinatura Pro/Max do claude.ai/Claude Code —
> a assinatura não dá acesso à API. São billings separados.

Alternativa ao `.env`: exportar no shell (`export ANTHROPIC_API_KEY=...`).

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
- `agents.<nome>.delay_segundos` — **opcional** (default `0`). Pausa em segundos **antes de cada
  chamada** daquele agente ao LLM, para não sobrecarregar o provider. Vale para **qualquer** provider
  (inclusive `anthropic:`/`google-gla:`), diferente do `ratelimit` que é RPM e só afeta os modelos
  custom. Ex.: `delay_segundos: 2` faz o nó esperar 2s antes de chamar.
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
- `mcp.{auto,incluir,excluir,config_path,agentes}` — **opcional**. Por padrão (`auto: true`) herda os
  servers MCP locais da sua sessão do Claude Code (com probe que descarta os quebrados) — nada a
  configurar. Detalhe na seção "MCP" abaixo.
- `websearch.{habilitado,provider,agentes,max_results}` — **opcional**. Por padrão **ligado**
  (DuckDuckGo, sem API key) para os 4 agentes: eles buscam conteúdo atualizado na internet durante o
  loop. Detalhe na seção "Web search" abaixo.
- `ratelimit.{requisicoes_por_minuto,max_retries}` — **opcional** (defaults **10** e **6**). Teto **global**
  de RPM (camada HTTP) + retries em 429/5xx. Detalhe na seção "Rate limit" abaixo.

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
chamam sozinhos durante a execução**, quando julgam necessário (buscar uma página do Confluence, ler
um ticket do Jira, etc.).

> **Só leitura (invariante, sempre ligado).** O loopforge **apenas consulta** os serviços externos via
> MCP — Jira, Confluence, OpenMetadata e quaisquer outros. **Nunca cria, edita ou apaga** nada neles.
> Toda toolset MCP passa por um filtro **fail-closed** antes de chegar aos agentes: tools de escrita
> (`create*`, `update*`, `delete*`, `patch*`, ...), de execução, ou de nome ambíguo são **removidas** —
> o modelo nem as enxerga. A **única** coisa que o sistema escreve é a SKILL gerada, gravada
> localmente em `skill.output_dir`. Não é configurável.

### Não precisa configurar — herda da sua sessão do Claude Code

Por padrão (`mcp.auto: true`), o loopforge **descobre sozinho** os servers MCP locais que você já tem
no Claude Code, mesclando (nesta ordem, o último vence):

1. `~/.claude.json` → `mcpServers` (global do usuário)
2. `~/.claude.json` → `projects[<seu-projeto>].mcpServers` (do projeto)
3. `./.mcp.json` (arquivo do projeto)

Então, se um server (ex.: `atlassian`/`confluence`/`jira`) já está habilitado no seu Claude Code,
ele aparece automaticamente para os agentes — sem nada no YAML. Adicione novos com `claude mcp add`.

> **Limitação importante:** connectors **hospedados no claude.ai** (autenticados por OAuth da
> sessão — ex.: os conectores Atlassian/Slack da interface) **não** ficam nesses arquivos e **não
> podem ser herdados** por um processo separado como o loopforge. Só servers **locais** (stdio/sse/http
> definidos em `~/.claude.json`/`.mcp.json`) são reaproveitados. Para Confluence/Jira, garanta que o
> server está configurado **localmente** (via `claude mcp add`), não só como conector do claude.ai.

### Resiliência e escopo

- **Probe:** cada server é testado ao iniciar — o loopforge conecta isolado **e lista as tools** (a
  mesma chamada que os agentes fazem em runtime). Os que falham são **descartados com um warning**:
  binário ausente, init quebrado (ex.: um server que precisa de um índice que não existe neste
  projeto), **ou que conectam mas erram ao enumerar as tools** (ex.: um server que depende de um
  recurso/índice que sumiu). Um server quebrado **nunca derruba** o loop.
- **Escopo:** por padrão o auto puxa *todos* os servers locais — inclusive dev-tooling irrelevante,
  que ainda floda modelos fracos com dezenas de tools (e pode quebrar o schema de modelos estritos
  como Gemma/Gemini, gerando `400`). Use `incluir`/`excluir` para focar nos serviços de domínio:

```yaml
mcp:
  auto: true                          # (default) herda da sessão; false desliga
  incluir: ["confluence", "jira"]     # allowlist (null = todos; [] = nenhum)
  excluir: ["tokensave"]              # denylist (aplicada depois do incluir)
  config_path: "./outro.mcp.json"     # override: aponta um JSON e DESLIGA o auto
  agentes: [discovery, plan, write]   # quais nós ganham as tools (Judge fora por padrão)
```

- **Sem servers, sem drama:** se a allowlist ficar vazia, nenhum server casar/sobreviver ao probe, ou
  `auto: false`, o loop simplesmente **roda sem tools MCP** — não é erro, os agentes trabalham só com
  o objetivo + contexto herdado.

Formato do JSON = `mcpServers` (o mesmo do Claude Desktop/Cursor/Claude Code):

```json
{
  "mcpServers": {
    "confluence": {"command": "npx", "args": ["-y", "mcp-confluence"],
                   "env": {"CONFLUENCE_TOKEN": "${CONFLUENCE_TOKEN}"}},
    "jira": {"command": "npx", "args": ["-y", "mcp-jira"]}
  }
}
```

### Como funciona

- Cada server vira uma toolset **prefixada pelo nome** (`confluence_*`, `jira_*`) — sem colisão.
- Variáveis de ambiente no JSON: `${VAR}` (obrigatória) ou `${VAR:-default}`.
- Os agentes em `mcp.agentes` recebem as tools e **decidem em runtime** quando chamá-las. O **Judge
  fica de fora por padrão** (avalia a skill sem viés de ferramenta).
- As conexões MCP são abertas no início do run e fechadas no fim (gerenciadas pelo runner). Na
  auto-descoberta, os servers mesclados vão para um arquivo temporário (0600) que é apagado logo
  após carregar as tools.

---

## Web search — agentes puxam conteúdo atual da internet

Cada agente combina o **raciocínio da sua LLM** com **busca na web** para fundamentar a skill em
conteúdo recente (libs novas, APIs atuais, best practices do momento) em vez de só confiar na memória
do modelo. É uma tool que o agente chama sozinho quando precisa — igual ao MCP, mas para a internet
aberta (não exige login/credencial de serviço).

Por padrão vem **ligado** com **DuckDuckGo** (sem API key) para os 4 agentes:

```yaml
websearch:
  habilitado: true
  provider: duckduckgo                       # duckduckgo (sem key) | tavily (TAVILY_API_KEY)
  agentes: [discovery, plan, write, judge]   # quais nós buscam na web
  max_results: 5                             # teto de resultados por busca (1..20)
```

- **DuckDuckGo** (default): zero config, sem API key — combina com modelos free. Qualidade média e
  pode rate-limitar em rajada.
- **Tavily**: otimizado para agentes, resultados mais limpos. Precisa de `TAVILY_API_KEY` no ambiente
  (free tier ~1000/mês) e da dep `tavily-python`. Sem a key **ou** sem a dep, a tool é **omitida com
  warning** — o loop segue só com o raciocínio (degrada suave, não quebra).
- **Escopo por agente:** restrinja com `agentes: [...]` (ex.: só `[discovery]` para concentrar a
  pesquisa na descoberta). `habilitado: false` desliga tudo.

> Como cada agente usa uma LLM diferente, a qualidade da busca + síntese varia conforme o modelo do nó.
> Modelos que não suportam tool-calling não conseguem chamar a tool — nesses, o agente ignora o web search.

---

## Rate limit (requisições por minuto)

Os providers limitam as requisições por minuto por chave — os modelos `:free` do OpenRouter têm limites
agressivos, e estourar resulta em `429 Too Many Requests` que derruba o loop. O `ratelimit` espaça as
chamadas para ficar dentro do teto.

```yaml
ratelimit:
  requisicoes_por_minuto: 10   # default 10
  max_retries: 6               # default 6
```

- **Global, não por nó.** Um único `.run()` de um agente pode disparar **várias** chamadas HTTP ao
  provider (o loop de tool-calling). Por isso o limite é aplicado na **camada HTTP**, num `httpx.AsyncClient`
  compartilhado pelos 4 agentes — o teto vale para a **soma** de todas as chamadas (nós + tool loops).
- **Retries (`max_retries`).** Quando uma chamada toma `429`/`5xx`, o SDK reenvia até `max_retries` vezes,
  respeitando o `Retry-After` do provider. Isso aguenta um `429` **transitório** (modelo `:free` saturado
  upstream). **Não** resolve cota diária estourada — nesse caso a chamada falha mesmo depois dos retries.
- **Quais modelos.** Vale para os modelos montados internamente (`openrouter:` e `nvidia:`). Os prefixos
  nativos do PydanticAI (`anthropic:`, `google-gla:`, `openai:`) não recebem o cliente limitado — esses
  providers pagos não costumam ter limites tão apertados.
- **Quando ainda toma 429:** abaixe `requisicoes_por_minuto` (ex.: 5 ou 3), reduza `loop.max_iteracoes`,
  troque de modelo/provider, ou adicione créditos no OpenRouter (free tier tem cota diária por chave). Um
  `429` que esgota os retries encerra o loop com mensagem clara (sem traceback).

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

Em **qualquer** dos 3 casos a skill é gravada (se houve artefato) e sai um log `resumo_final`
(status, iterações, score_final, melhor_score, caminho). O loop não é derrubado se o Judge falhar ao
montar o veredito: ele cai num fallback (notas 0) e o loop encerra normalmente, preservando a skill
escrita. Agentes usam `retries=3` para o modelo corrigir saídas tipadas inválidas antes de desistir.

---

## Observabilidade

- **Logs estruturados** (structlog + rich) — cada transição de nó, score por dimensão e decisão de
  loop no terminal. Sempre ligado. Antes de cada chamada ao LLM sai um `estagio_inicio` com o nó, a
  iteração, o `delay` aplicado e o **prompt enviado** (resumido); ao terminar, cada nó loga um `*_ok`
  com um **resumo do retorno**. No fim sai um `resumo_final` com status, iterações, scores e o caminho
  da skill gravada.
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
