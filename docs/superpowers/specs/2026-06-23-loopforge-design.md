# Design — Loop Engineer (`loopforge`)

**Data:** 2026-06-23
**Status:** aprovado (brainstorming) → pronto p/ writing-plans

## Objetivo

Aplicação Python que implementa **Loop Engineering**: orquestração multi-agente (cada agente numa LLM
distinta) que produz uma **SKILL do Claude** de alta qualidade a partir de um objetivo declarado em YAML,
iterando até atingir uma métrica de qualidade ou um teto de iterações.

## Decisões fechadas (brainstorming)

1. **Topologia:** 4 nós — `Discovery → Plan → Write → Judge` (separar planejar de escrever cria gate de
   qualidade antes de gastar tokens escrevendo).
2. **Métrica:** score composto **híbrido** — checks determinísticos (0.30) + LLM-as-judge rubricado (0.70).
   Rejeitadas: métrica matemática pura (arbitrária) e bibliotecas NLP (não há skill de referência).
3. **Observabilidade:** LangGraph Studio (`langgraph dev`) + logs estruturados (structlog/rich).
4. **Providers:** Anthropic + Google (Gemini). Anti-viés: **Judge usa provider ≠ Write**.

## Arquitetura

### Grafo (LangGraph)

```
objetivo ─▶ discovery ─▶ plan ─▶ [gate_plano] ─▶ write ─▶ judge ─▶ [decide_loop]
                          ▲                                              │
                          └────── reprovado & iter<max (c/ feedback) ────┘
```

- **discovery** (Gemini) — pesquisa soluções/tecnologias; roda 1x (re-roda só se Judge sinalizar
  research insuficiente). Tools: WebSearch + MCP.
- **plan** (Claude) — produz `SkillPlan` (estrutura, frontmatter planejado, arquivos, triggers). Nó que itera.
- **gate_plano** — edge condicional: plano tem campos mínimos? senão volta pro plan.
- **write** (Claude) — escreve `SKILL.md` + arquivos referenciados → `SkillArtifact`.
- **judge** (Gemini) — produz `JudgeVerdict` (notas por dimensão + rationale + feedback).
- **decide_loop** — edge condicional: aprovado / reitera / para (ver "Controle de loop").

### Mapeamento LLM (default, editável no YAML)

`discovery=gemini`, `plan=claude`, `write=claude`, `judge=gemini`.

### Estado do grafo (Pydantic)

`objetivo: str`, `contexto: Contexto`, `discovery_report`, `plan: SkillPlan | None`,
`skill_artifact: SkillArtifact | None`, `score_atual: float`, `judge_feedback: str | None`,
`iteracao: int`, `historico: list[IteracaoRegistro]`.

### Persistência / memory spine

Checkpointer **SqliteSaver** do LangGraph em `.loopforge/runs/<run_id>.sqlite`. Serve a (a) memory spine
entre runs / resume e (b) time-travel no Studio.

## Métrica (detalhe)

```
score_final = 0.30 · score_det + 0.70 · score_judge
```

**Determinístico** (cada check 0..1; pesos somam 1.0): `frontmatter_valido` 0.25, `description_tem_trigger`
0.25, `dentro_budget` 0.20, `refs_existem` 0.15, `markdown_valido` 0.15. `budget_linhas`=500.
Budget pontua `1.0` se ≤ teto, senão `max(0, 1 − (linhas − budget)/budget)`.

**Judge** (rubrica, nota LLM 0..1; pesos somam 1.0): `alinhamento_objetivo` 0.30, `discoverability` 0.20,
`concisao_clareza` 0.15, `completude` 0.20, `aderencia_best_practices` 0.15.

Exemplo numérico completo e tabela de significados: ver `README.md`.

## Controle de loop (saída garantida)

Para em qualquer condição: `score_final ≥ score_minimo` (aprovado) | `iteracao ≥ max_iteracoes`
(parcial) | score estagnado por `no_progress_paciencia` iterações (estagnação → escala).

## best_practices SKILL

`skill.best_practices` = path p/ SKILL com regras Asaas. **Injetada como contexto herdado** em todos os
agentes **e** pontuada pelo Judge (`aderencia_best_practices`). Opcional (null = pula a dimensão, renormaliza pesos).

## Estrutura do projeto

```
pyproject.toml          # uv; deps: pydantic-ai, langgraph, langgraph-cli, pyyaml, typer, rich, structlog
langgraph.json          # expõe o grafo compilado p/ `langgraph dev`
config.example.yaml     # config anotada (FEITO)
README.md               # docs + pesos + exemplos (FEITO)
src/loopforge/
  config.py             # schema Pydantic do YAML + validate
  state.py              # estado do grafo + models (SkillPlan, SkillArtifact, JudgeVerdict)
  context.py            # carrega docs/links/best_practices → contexto herdado
  agents/{discovery,plan,write,judge}.py   # 1 Agent PydanticAI cada
  scoring/{deterministic,rubric,composite}.py
  graph.py              # StateGraph + edges condicionais + checkpointer
  persistence.py        # grava skill final no output_dir
  logging.py            # setup structlog/rich
  cli.py                # loopforge run/validate (+ --doc/--link)
tests/                  # pytest; agentes mockados via TestModel/FunctionModel
```

## Testes

- `config`: load + validação (campos faltando, paths inválidos, pesos que não somam 1.0).
- `scoring`: cada check determinístico isolado; fórmula de budget; composição ponderada.
- `loop`: termina por score, por max_iter, por no-progress.
- `graph`: caminho aprovado vs reprovado→reitera (agentes mockados via TestModel).

## Fora de escopo (YAGNI)

- Teste comportamental da skill (sub-agente roda a skill) — fica como extensão futura opcional.
- Providers além de Anthropic/Gemini.
- UI além do Studio + logs.

## Riscos / observações

- Multi-provider exige chaves (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`). Sem 2 providers, degrada p/
  modelos Anthropic distintos (opus/sonnet/haiku) mantendo Judge≠Write.
- "O avaliador lê o transcript, não os arquivos": o Judge avalia o `SkillArtifact` em disco, não a
  conversa — evita a pegadinha clássica de loop engineering.
- `CLAUDE.md` tem schema YAML antigo (`agents.validation`, sem `write`/`scoring`/`best_practices`).
  Sync pendente — confirmar com usuário (instrução foi documentar só no README por ora).
