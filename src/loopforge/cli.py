"""CLI do loopforge (Typer)."""

from __future__ import annotations

import asyncio

import typer
from langgraph.errors import GraphRecursionError
from openai import APIStatusError
from pydantic_ai.exceptions import (
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from rich.console import Console

from loopforge.config import load_config
from loopforge.logging import setup_logging
from loopforge.runner import run_loop

DEFAULT_CONFIG = "config.yaml"

app = typer.Typer(
    help="Loop Engineer: gera SKILLs do Claude via loop multi-agente.",
    no_args_is_help=False,
)
console = Console()


def _executar(config: str, doc: list[str] | None, link: list[str] | None, verbose: bool) -> None:
    """Roda o loop e imprime o resultado.

    Args:
        config: caminho do YAML de configuração.
        doc: diretórios/arquivos de doc extra (estendem o YAML).
        link: URLs extra (estendem o YAML).
        verbose: ativa log DEBUG.
    """
    setup_logging(verbose=verbose)
    try:
        final = asyncio.run(run_loop(config, extra_docs=doc, extra_links=link))
    except (ModelHTTPError, APIStatusError) as e:
        # Erro vindo do provider de LLM (ex: 429 do free tier do OpenRouter após
        # esgotar os retries). Encerra limpo, sem despejar o traceback inteiro.
        status = getattr(e, "status_code", None)
        if status == 429:
            console.print(
                "[red]Provider de LLM limitou as requisições (HTTP 429).[/red] Mesmo "
                "com os retries, o limite persistiu — provável cota diária do free tier. "
                "Opções: aumentar [bold]ratelimit.max_retries[/bold], baixar "
                "[bold]ratelimit.requisicoes_por_minuto[/bold] e [bold]loop.max_iteracoes[/bold], "
                "trocar de modelo/provider, ou adicionar créditos no OpenRouter."
            )
        else:
            console.print(f"[red]Erro do provider de LLM (HTTP {status}):[/red] {e}")
        raise typer.Exit(code=1)
    except UnexpectedModelBehavior as e:
        # Algum agente (ex: write/plan) não conseguiu produzir a saída tipada nem
        # após os retries. O Judge tem fallback próprio; aqui pegamos os demais.
        console.print(
            f"[red]Um agente não produziu uma saída válida:[/red] {e}\n"
            "Dica: use um modelo mais robusto nesse agente (saída tipada/tool-calling), "
            "ou desligue o web search dele em [bold]websearch.agentes[/bold]."
        )
        raise typer.Exit(code=1)
    except UsageLimitExceeded as e:
        console.print(f"[red]Limite de uso do agente atingido:[/red] {e}")
        raise typer.Exit(code=1)
    except GraphRecursionError as e:
        console.print(
            f"[red]O grafo excedeu o limite de passos:[/red] {e}\n"
            "Baixe [bold]loop.max_iteracoes[/bold] ou verifique a lógica do loop."
        )
        raise typer.Exit(code=1)
    cor = "green" if final.status == "aprovado" else "yellow"
    console.print(
        f"[{cor}]Loop encerrado[/{cor}] — status={final.status} "
        f"score_final={final.score_final:.4f} iterações={final.iteracao}"
    )


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Sem subcomando, roda o loop lendo `config.yaml` do diretório atual."""
    if ctx.invoked_subcommand is None:
        _executar(DEFAULT_CONFIG, None, None, False)


@app.command()
def validate(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Caminho do YAML."),
) -> None:
    """Valida o YAML sem executar o loop."""
    load_config(config)  # levanta ValidationError/FileNotFoundError se inválido
    console.print(f"[green]Configuração válida:[/green] {config}")


@app.command()
def run(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Caminho do YAML."),
    doc: list[str] = typer.Option(None, "--doc", help="Diretório/arquivo de doc extra (repetível)."),
    link: list[str] = typer.Option(None, "--link", help="URL extra (repetível)."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Executa o loop e grava a SKILL resultante."""
    _executar(config, doc, link, verbose)
