# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Status do repositório:** projeto em estágio inicial (greenfield). Este documento descreve a
> arquitetura-alvo e as convenções acordadas. Ao implementar, mantenha este arquivo sincronizado
> com a estrutura real conforme o código for surgindo.

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
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  DISCOVERY   │───▶│     PLAN     │───▶│  VALIDAÇÃO   │
│ (LLM A)      │    │ (LLM B)      │    │ (LLM C)      │
│ levanta      │    │ elabora      │    │ julga se a   │
│ soluções,    │    │ plano de     │    │ SKILL atinge │
│ tecnologias, │    │ execução     │    │ o objetivo   │
│ estratégias  │    │              │    │              │
└──────────────┘    └──────────────┘    └──────┬───────┘
        ▲                                       │
        │         reprovado (abaixo do          │
        └───────── threshold de métrica) ───────┤
                                                │ aprovado
                                                ▼
                                          SKILL final
```

- **Discovery Agent** — faz *discovery* de soluções tecnológicas, melhores caminhos e estratégias.
- **Plan Agent** — elabora o plano de execução com base no discovery.
- **Validation/Judge Agent** — avalia se o plano está coerente com o objetivo e **julga** se a
  SKILL devolvida está de acordo e vai atingir o objetivo definido pelo usuário.
- O loop **reitera** enquanto a métrica de avaliação ficar abaixo do threshold, respeitando um
  **limite máximo de iterações** (proteção contra loop infinito).

## Stack

| Camada | Tecnologia | Papel |
|--------|-----------|-------|
| Gerenciador de pacotes | **uv** | Ambiente, dependências e execução (`uv sync`, `uv run`) |
| Agentes de IA | **PydanticAI** | Definição de cada agente, *tools* e integração **MCP** (todo o harness possível) |
| Orquestração | **LangGraph** | Grafo que conecta Discovery → Plan → Validação, com aresta de loop condicional e threshold |
| Interface | **CLI `loopforge`** (documentada no `README.md`) | Executar comandos e passar recursos extras (links, diretórios de docs) como contexto |
| Configuração | **YAML** | Arquivo lido antes da execução (LLM de cada agente, objetivo da SKILL, limite de iterações) |
| Observabilidade | Logs estruturados + **LangGraph (visualização do grafo)** | Acompanhar a execução em tempo real |

## Arquivo de configuração YAML

A aplicação **lê o YAML antes da execução**. Campos obrigatórios:

1. **LLM de cada agente** — `discovery`, `plan`, `validation` (cada um pode ser uma LLM distinta).
2. **Objetivo da SKILL** — o alvo que o loop deve atingir.
3. **Limite de iterações** — teto do loop (anti loop-infinito).

Esquema oficial das chaves (formato de `model` segue o padrão PydanticAI `provider:modelo`):

```yaml
agents:
  discovery:
    model: anthropic:claude-opus-4-8     # LLM do agente de Discovery
  plan:
    model: openai:gpt-4o                  # LLM do agente de Plan
  validation:
    model: google-gla:gemini-2.0-flash    # LLM do agente de Validação/Judge

skill:
  objetivo: "<objetivo definido pelo usuário>"
  output_dir: "./skills"                  # onde a SKILL final é gravada

loop:
  max_iteracoes: 5         # threshold de iterações (anti loop-infinito)
  score_minimo: 0.8        # threshold de qualidade p/ aprovar a SKILL (0.0–1.0)

contexto:                  # opcional; também passável via flags da CLI
  docs: []                 # lista de diretórios de documentação
  links: []                # lista de URLs
```

Chaves canônicas: `agents.{discovery,plan,validation}.model`, `skill.objetivo`,
`skill.output_dir`, `loop.max_iteracoes`, `loop.score_minimo`, `contexto.docs`, `contexto.links`.

> Cada agente usa uma LLM **diferente** por design — isso é central ao conceito. Não force todos
> os agentes para o mesmo provider/modelo sem instrução explícita.

## Conceitos centrais (ao implementar, respeitar)

- **Papéis isolados por LLM** — Discovery, Plan e Validação são agentes PydanticAI separados, cada
  um com seu modelo configurado via YAML. Evite acoplar lógica entre eles fora do grafo.
- **Loop com saída garantida** — a condição de continuação do LangGraph deve checar **tanto** a
  métrica de avaliação (`loop.score_minimo`) **quanto** o contador de iterações (`loop.max_iteracoes`).
  Sair do loop SEMPRE que qualquer um dos dois for atingido.
- **Métricas de avaliação** — o agente de Validação produz uma pontuação/veredito estruturado
  (PydanticAI → saída tipada). É essa métrica que alimenta a decisão de loop.
- **Contexto incremental via CLI** — links e diretórios de documentação passados na CLI são
  injetados como contexto adicional na execução dos agentes (tools/MCP). Trate-os como entrada,
  não hardcode.
- **Observabilidade dupla** — toda execução emite (a) logs estruturados e (b) é inspecionável pela
  visualização de grafo do LangGraph. Não remova/silencie instrumentação ao refatorar.

## Comandos

> ⚠️ Convenções-alvo. Confirme/atualize conforme o `pyproject.toml`/`README.md` reais forem criados.
> A CLI `loopforge` é **documentada no `README.md`** (fonte de verdade dos comandos e flags).

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

# Adicionar/remover dependências:
uv add <pacote>
uv remove <pacote>
```

Ao definir os comandos reais, **atualize esta seção e o `README.md` juntos** — eles não devem
divergir.
