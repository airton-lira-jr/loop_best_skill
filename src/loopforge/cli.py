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
def validate(
    config: str = typer.Option(..., "--config", "-c", help="Caminho do YAML."),
) -> None:
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
