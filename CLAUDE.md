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
| Agentes de IA | **PydanticAI** | Define cada agente, *tools*, integração **MCP** + **web search** (todo harness possível) |
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
    delay_segundos: 0                      # opcional; pausa (s) antes de cada chamada deste agente
  plan:
    model: anthropic:claude-opus-4-8       # LLM do agente de Plan
  write:
    model: anthropic:claude-opus-4-8       # LLM do agente de Write
  judge:
    model: google-gla:gemini-2.0-flash     # LLM do agente de Validação/Judge

skill:
  objetivo: "<texto OU path .md/diretório>" # texto literal ou path (arquivo/dir de .md) → lido
  output_dir: "./skills"                  # onde a SKILL final é gravada
  best_practices: null                    # opcional; path p/ uma SKILL com regras 

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

websearch:                  # opcional; tool de busca na web dada aos agentes
  habilitado: true          # default true
  provider: duckduckgo      # duckduckgo (sem API key) | tavily (lê TAVILY_API_KEY)
  agentes: [discovery, plan, write, judge]  # nós que buscam na web
  max_results: 5            # teto por busca (1..20)

ratelimit:                  # opcional; resiliência às APIs dos providers
  requisicoes_por_minuto: 10  # default 10; teto RPM GLOBAL (camada HTTP), p/ não estourar 429
  max_retries: 6              # default 6; reenvia em 429/5xx (respeita Retry-After). 0 = sem retry
```

> **Anti-viés (default, validado):** `agents.judge.model` deve usar provider **≠** `agents.write.model`,
> p/ avaliador não ser cúmplice de quem escreveu. 4 nós do grafo: `discovery`, `plan`,
> `write`, `judge`. `AgentsCfg._checa_anti_vies` (config.py) emite **warning** estruturado
> (`judge_write_mesmo_modelo`) se `judge.model == write.model` — não bloqueia o load, só avisa.

> **Chaves de API:** NÃO vão no YAML. PydanticAI lê do ambiente
> (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`).
> Dois prefixos NÃO são nativos do PydanticAI e `builder._resolver_modelo` os monta na mão como
> `OpenAIChatModel` (endpoint OpenAI-compatible): `nvidia:` (NVIDIA NIM, API gratuita em
> `build.nvidia.com`, lê `NVIDIA_API_KEY`) e `litellm:` (LiteLLM Proxy self-hosted, sem endpoint
> fixo, lê `LITELLM_BASE_URL` obrigatória + `LITELLM_API_KEY` opcional — proxy sem `master_key` não
> exige chave). `_precisa_cliente_rate_limited` decide se monta o `http_client` compartilhado (RPM +
> retries) olhando esses mesmos prefixos. `run_loop` carrega `.env`
> via `loopforge.env.carregar_env` (override=False; shell vence). São API keys (cobrança por token),
> não a assinatura Pro/Max — **por design, o loopforge não suporta autenticar via login/OAuth do
> Claude Code/claude.ai** (`CLAUDE_CODE_OAUTH_TOKEN` ou similar): usar credenciais de assinatura em
> ferramenta de terceiros viola os Termos de Serviço da Anthropic e está bloqueado no servidor deles
> desde abr/2026 (ver [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)).

Chaves canônicas: `agents.{discovery,plan,write,judge}.model` (+ `.delay_segundos`, opcional, default 0), `skill.objetivo`,
`skill.output_dir`, `skill.best_practices` (opcional), `loop.max_iteracoes`, `loop.score_minimo`,
`loop.no_progress_paciencia`, `scoring.pesos.{deterministico,judge}`,
`scoring.deterministico.*`, `scoring.judge.*`, `contexto.docs`, `contexto.links`,
`mcp.auto` (default true), `mcp.dinamico` (default true), `mcp.config_path` (override opcional), `mcp.agentes`,
`mcp.judge_verificacao` (default false),
`websearch.{habilitado,provider,agentes,max_results}`,
`ratelimit.{requisicoes_por_minuto,max_retries}` (defaults 10, 6).

> Validação de pesos estrita: `scoring.pesos`, `scoring.deterministico` (5 checks),
> `scoring.judge` (5 dimensões) — **cada grupo deve somar 1.0**, senão load levanta `ValidationError`.

> Cada agente usa LLM **diferente** por design — central ao conceito. Não force todos
> agentes p/ mesmo provider/modelo sem instrução explícita.

## Conceitos centrais (ao implementar, respeitar)

- **Papéis isolados por LLM** — Discovery, Plan, Write, Judge são agentes PydanticAI separados, cada
  um com modelo configurado via YAML. Evite acoplar lógica entre eles fora do grafo.
- **Trilha de documentação (handoff)** — cada agente DOCUMENTA seu raciocínio na própria saída tipada
  p/ o próximo usar como fundamento: Discovery grava `achados`+`fontes` (a pesquisa não evapora); Plan
  grava `secoes`+`notas_para_write` (decisões p/ o Write); Write grava `notas_de_escrita` (o que fez e
  por quê). O grafo propaga isso adiante (`_discovery_texto`/`_plan_texto`/`_arquivos_texto` em
  `graph.py`): Write vê Discovery+Plano+artefato anterior+feedback (na reiteração **revisa**, não
  regenera); **Judge vê Plano + arquivos referenciados + notas do Write**, não só o `SKILL.md` (antes
  ele era cego pras refs). Princípio: o avaliador lê o que está no estado, não os arquivos no disco.
- **Prompts = best practices de skill embutidas** — `prompts.py` codifica as regras de autoria
  (`SKILL_RULES`): `description` = QUANDO usar (3ª pessoa, "Use quando…", sem resumir o passo a passo),
  `name` em hífens, corpo conciso, progressive disclosure p/ refs. O `WRITE_SYS` é um **contrato**
  (formato de receita, não proibição) que casa 1:1 com os checks determinísticos (fences `---`, trigger,
  orçamento de linhas, refs relativas existentes). Ao mexer num check, ajuste o prompt junto.
- **Loop com saída garantida** — `decidir_loop` (em `graph.py`) checa **score** (`loop.score_minimo`),
  **teto de iterações** (`loop.max_iteracoes`) **e** estagnação (`loop.no_progress_paciencia`). Sai do
  loop SEMPRE que qualquer um for atingido: `aprovado`, `max_iter` ou `estagnado`.
- **Métrica híbrida** — score composto: `score_final = pesos.deterministico * det + pesos.judge * jdg`.
  Camada determinística roda checks programáticos sobre `SkillArtifact`; camada judge é rubrica
  do Judge (saída tipada `JudgeVerdict`). Sem `best_practices`, dimensão `aderencia_best_practices`
  dropa, pesos do judge renormalizam.
- **Judge calibrado (rigor + baixo ruído)** — como `score_judge` pesa 0.70 do score final, o Judge é o
  maior fator de acurácia do loop. `JUDGE_SYS` (prompts.py) recebe o mesmo `SKILL_RULES` que Plan/Write,
  exige citar trecho concreto como evidência por dimensão, dá âncoras do que cada faixa de nota
  significa, e instrui a resistir à tendência de LLM-juiz inflar nota. `JudgeVerdict` (state.py) tem
  `problemas_bloqueantes`/`sugestoes` (listas) além de `feedback_acionavel` (resumo) — `graph._feedback_texto`
  renderiza isso como checklist para Plan/Write, em vez de prosa livre a interpretar. Judge e Write
  rodam com `model_settings=ModelSettings(temperature=...)` baixo (`builder.JUDGE_TEMPERATURE=0.1`,
  `WRITE_TEMPERATURE=0.3`) — reduz variância de rodada a rodada; Discovery fica na temperatura default
  do provider (exploração se beneficia de diversidade). Os checks determinísticos também foram
  endurecidos: `_TRIGGER` (scoring/deterministic.py) ancora "Use quando/Use when" no INÍCIO da
  description (não em qualquer posição); o parse de frontmatter normaliza CRLF antes de rodar as
  regexes, pra não zerar `frontmatter_valido`/`markdown_valido` por formatação incidental do provider.
- **best_practices como contexto herdado (opcional)** — quando `skill.best_practices` aponta p/
  SKILL, conteúdo injeta nos prompts de todos agentes **e** Judge pontua. Ausente
  (null/omitido/arquivo inexistente) ⇒ dimensão `aderencia_best_practices` dropa, renormaliza.
- **MCP autônomo (opcional, auto por padrão)** — `mcp_discovery.preparar_mcp_config` (async): descobre
  servers MCP **locais** da sessão (`descobrir_mcp_servers`: mescla `~/.claude.json` global+projeto e
  `.mcp.json`), aplica `incluir`/`excluir`, faz **probe** de cada um (conecta isolado **e lista as
  tools** — mesmo exercício do runtime, então um server que conecta mas erra no `list_tools` também é
  pego; os que falham são **descartados** — server quebrado nunca derruba o loop), grava JSON
  temporário (0600) só com saudáveis,
  injeta em `mcp.config_path`. `mcp.config_path` explícito é override, desliga auto. Agentes em
  `mcp.agentes` recebem toolsets via `load_mcp_toolsets`, chamam em runtime; runner abre/fecha conexões
  em volta do `ainvoke` (`async with agent`). Judge sem tools por padrão — `mcp.judge_verificacao: true`
  (default false) dá as MESMAS tools (já read-only) só pro Judge CONFERIR fatos citados pelo
  Discovery/Plan (não é viés de geração de conteúdo, é verificação). Connectors do claude.ai
  (OAuth) NÃO herdáveis — só servers locais (stdio/sse/http no `mcpServers`). `incluir: []`/sem
  sobreviventes/`auto: false` ⇒ loop roda **sem MCP** (não é erro; agentes usam só objetivo + contexto).
- **Seleção DINÂMICA de MCP por contexto (`mcp.dinamico`, default true)** — quando `incluir is None` e
  `dinamico`, `selecionar_por_contexto` escolhe **automaticamente** os servers relevantes ao objetivo:
  cruza os tokens do contexto (hosts dos `contexto.links` + palavras do objetivo + nomes dos docs) com a
  **assinatura** de cada server (nome + command + args + host do endpoint + **chaves de env**, ex.
  `CONFLUENCE_URL`→`confluence`). Casou ⇒ entra (loga `mcp_selecionado` com os tokens); senão
  `mcp_descartado_contexto`. É pré-probe e determinístico (sem LLM). Assim, trocar os links do
  `contexto` muda o MCP usado sem editar `incluir`. `incluir` como lista é **override manual** (ignora o
  dinâmico); `dinamico: false` + `incluir: None` ⇒ todos (legado). Limite conhecido: server relevante
  só pelas DESCRIÇÕES das tools (nome/env não batem) não casa pré-probe — force via `incluir`.
- **Read-only nos serviços externos (INVARIANTE, sempre ligado)** — a aplicação só **consulta**
  Jira/Confluence/OpenMetadata e afins via MCP; **nunca cria/edita/apaga** neles. Toda toolset MCP
  passa por `mcp_readonly.filtro_readonly` (em `builder._toolsets_para`) antes de chegar ao agente:
  filtro **fail-closed** — tool de escrita, execução ou de nome ambíguo é removida e o LLM nem a vê
  (classificação por verbo no nome, snake+camelCase, + annotation `readOnlyHint`). Única escrita do
  sistema = a SKILL gerada, gravada localmente por `gravar_skill`. Não é configurável; não afrouxe.
- **Web search (atualidade)** — `websearch.construir_websearch_tools` dá aos agentes (os listados em
  `websearch.agentes`) uma tool de busca na internet (`duckduckgo_search` ou `tavily_search`) p/
  fundamentar a skill em conteúdo recente, somado ao raciocínio da LLM. Wireada em `build_agents` via
  `tools=`. Default: DuckDuckGo (sem key), 4 agentes. **Cuidado em teste:** `TestModel` chama TODA tool
  registrada — então nos testes que rodam agentes via TestModel, ponha `websearch.habilitado: False`
  senão dispara request real à rede. Tavily degrada suave (sem key/sem dep `tavily-python` ⇒ tool omitida).
- **Rate limit + retries (providers free)** — `ratelimit.requisicoes_por_minuto` (default 10) limita
  as chamadas às APIs dos providers na **camada HTTP**, não por nó: `ratelimit.criar_cliente_rate_limited`
  cria um `httpx.AsyncClient` com event hook de request, compartilhado pelos 4 agentes em `build_agents`,
  então o teto é **global** (soma das chamadas dos nós **+ os loops de tool-calling**, que o controle por
  nó não veria). `ratelimit.max_retries` (default 6) é passado ao `AsyncOpenAI` (via `_async_openai`) p/
  reenviar em 429/5xx respeitando o `Retry-After` — sobe a resiliência a 429 **transitório** (modelo free
  saturado upstream), mas **não** resolve cota diária estourada. Tudo isso só vale pros modelos montados
  internamente (`openrouter:`/`nvidia:`); os prefixos nativos do PydanticAI (`anthropic:`/`google-gla:`)
  não recebem o cliente. Sem `OPENROUTER_API_KEY`, `openrouter:` cai de volta na string nativa (sem rate
  limit/retries custom) — preserva build sem chaves em teste. Na CLI, um 429 que esgota os retries é
  capturado em `cli._executar` e encerra limpo (sem traceback), com dica de como ajustar.
- **Delay por agente (anti-sobrecarga)** — `agents.<nome>.delay_segundos` (default 0) é uma pausa
  (`asyncio.sleep`) aplicada em `graph._executar_agente` ANTES de cada chamada daquele nó ao LLM.
  Diferente do `ratelimit` (RPM, global, só camada HTTP dos modelos custom), o delay vale p/
  **qualquer** provider, inclusive os nativos (`anthropic:`/`google-gla:`). Use p/ espaçar as chamadas
  e não saturar o provider sem mexer no RPM global.
- **Logs por estágio** — `graph._executar_agente` loga `estagio_inicio` (nó/`agente`, `modelo`,
  iteração, delay e prompt resumido por `_resumir`, truncado) antes de chamar o LLM e `estagio_fim`
  depois; cada nó loga seu `*_ok` com um resumo do retorno. Não remova o `estagio_inicio` ao refatorar —
  é o ponto único de instrumentação de entrada. No fim, `runner.run_loop` emite **`resumo_final`**
  (status, iterações, score_final, melhor_score, caminho da skill).
- **Resiliência a saída inválida (loop nunca crasha por isso)** — agentes são montados com `retries=3`
  (`builder.RETRIES_OUTPUT`): o PydanticAI reenvia ao modelo quando o output não bate o `output_type`
  (modelos abertos erram JSON aninhado). Se o **Judge** ainda assim estourar `UnexpectedModelBehavior`/
  `UsageLimitExceeded`, `judge_node` usa `_verdict_fallback` (notas 0 + feedback) em vez de derrubar o
  grafo — a iteração conta como reprovada, o loop segue/para normalmente e **a skill escrita até então é
  gravada**. Os demais nós (write/plan/discovery) que falharem propagam e a CLI (`cli._executar`)
  encerra limpo (sem traceback). `recursion_limit` do grafo é derivado de `loop.max_iteracoes`
  (em `runner._rodar_grafo`) p/ não estourar o default 25 do LangGraph com `max_iteracoes` alto.
- **Contexto incremental via CLI** — links e diretórios de doc passados na CLI (`--doc`/`--link`)
  estendem `contexto.docs`/`contexto.links` do YAML. Trate como entrada, não hardcode.
- **`RUN.md` (trilha em disco)** — ao gravar a skill, `persistence.gravar_run_md` materializa um
  `RUN.md` ao lado do `SKILL.md` com a trilha do loop (achados/fontes do Discovery, spec+notas do Plan,
  notas do Write, último veredito do Judge, histórico de scores). É a versão inspecionável/auditável do
  que trafega no estado. `gravar_skill` sanitiza o caminho de cada arquivo referenciado
  (`_arquivo_destino`, fail-closed): URL/absoluto/`..` nunca escrevem fora do diretório da skill.
- **Observabilidade dupla** — toda execução emite (a) logs estruturados (structlog/rich) e (b)
  inspecionável no LangGraph Studio (`langgraph.json` → `graph_app.py:graph`). Checkpointer SQLite em
  `.loopforge/runs/` serve de memory spine + time-travel. Não remova/silencie instrumentação ao refatorar.
  > **Gotcha:** o grafo roda via `graph.ainvoke` (async), então o checkpointer tem que ser
  > `AsyncSqliteSaver` (`async with`), **não** o `SqliteSaver` síncrono — esse levanta
  > `NotImplementedError` no `aget_tuple`. Requer `aiosqlite`.
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