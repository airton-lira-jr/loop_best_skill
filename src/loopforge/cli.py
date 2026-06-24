"""CLI do loopforge (Typer)."""

from __future__ import annotations

import asyncio

import typer
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
    final = asyncio.run(run_loop(config, extra_docs=doc, extra_links=link))
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
