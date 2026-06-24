"""Montagem do contexto herdado injetado nos agentes.

Resolve, de fato, as fontes de referência declaradas no YAML/CLI:

- ``contexto.docs`` — paths de arquivos ou diretórios; o conteúdo dos
  arquivos de texto é lido (diretórios são percorridos recursivamente).
- ``contexto.links`` — URLs; o conteúdo de cada uma é baixado via HTTP.
- ``skill.best_practices`` — path de uma SKILL cujo conteúdo é lido.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from loopforge.config import AppConfig
from loopforge.logging import get_logger
from loopforge.state import Contexto, FonteConteudo

log = get_logger("context")

# Extensões tratadas como texto ao percorrer um diretório de docs.
_EXTENSOES_TEXTO = {
    ".md", ".txt", ".rst", ".markdown", ".py", ".yaml", ".yml", ".json",
    ".toml", ".ini", ".cfg", ".js", ".ts", ".tsx", ".jsx", ".go", ".java",
    ".kt", ".swift", ".rb", ".rs", ".sh", ".sql", ".html", ".css", ".env",
}
# Teto por arquivo (bytes) — evita estourar o contexto com arquivos enormes.
_MAX_BYTES = 200_000
# Timeout de cada requisição HTTP ao buscar um link.
_TIMEOUT_HTTP = 15.0

# Tipo do fetcher de links: recebe a URL, devolve o corpo ou None (falha).
Fetcher = Callable[[str], str | None]


def _ler_texto(caminho: Path) -> str | None:
    """Lê um arquivo como UTF-8; None se for grande demais, binário ou ilegível.

    Args:
        caminho: arquivo a ler.

    Returns:
        Conteúdo do arquivo, ou None se não puder/dever ser lido.
    """
    try:
        if caminho.stat().st_size > _MAX_BYTES:
            log.warning("doc_grande_ignorado", arquivo=str(caminho))
            return None
        return caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("doc_ilegivel_ignorado", arquivo=str(caminho), erro=str(exc))
        return None


def _coletar_docs(paths: list[str]) -> list[FonteConteudo]:
    """Lê o conteúdo dos paths de doc (arquivos diretos ou diretórios).

    Arquivos são lidos diretamente. Diretórios são percorridos
    recursivamente, lendo só arquivos de texto (ver ``_EXTENSOES_TEXTO``) e
    ignorando arquivos/pastas ocultos. Paths inexistentes são ignorados.

    Args:
        paths: lista de caminhos de arquivos e/ou diretórios.

    Returns:
        Lista de FonteConteudo com o conteúdo lido.
    """
    fontes: list[FonteConteudo] = []
    for p in paths:
        caminho = Path(p)
        if caminho.is_file():
            texto = _ler_texto(caminho)
            if texto is not None:
                fontes.append(FonteConteudo(origem=str(caminho), conteudo=texto))
        elif caminho.is_dir():
            for arquivo in sorted(caminho.rglob("*")):
                if not arquivo.is_file():
                    continue
                if arquivo.suffix.lower() not in _EXTENSOES_TEXTO:
                    continue
                rel = arquivo.relative_to(caminho)
                if any(parte.startswith(".") for parte in rel.parts):
                    continue  # pula arquivos/pastas ocultos
                texto = _ler_texto(arquivo)
                if texto is not None:
                    fontes.append(FonteConteudo(origem=str(arquivo), conteudo=texto))
        else:
            log.warning("doc_inexistente_ignorado", path=p)
    return fontes


def _fetch_padrao(url: str) -> str | None:
    """Baixa o corpo de uma URL via HTTP GET; None em qualquer falha.

    Args:
        url: endereço a buscar.

    Returns:
        Corpo da resposta como texto, ou None se a requisição falhar.
    """
    try:
        resp = httpx.get(url, timeout=_TIMEOUT_HTTP, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        log.warning("link_fetch_falhou", url=url, erro=str(exc))
        return None


def _coletar_links(links: list[str], fetcher: Fetcher) -> list[FonteConteudo]:
    """Busca o conteúdo de cada link; ignora os que falharem.

    Args:
        links: lista de URLs.
        fetcher: função que baixa uma URL (devolve None em falha).

    Returns:
        Lista de FonteConteudo dos links baixados com sucesso.
    """
    fontes: list[FonteConteudo] = []
    for url in links:
        texto = fetcher(url)
        if texto is not None:
            fontes.append(FonteConteudo(origem=url, conteudo=texto))
    return fontes


def build_contexto(
    config: AppConfig,
    extra_docs: list[str] | None = None,
    extra_links: list[str] | None = None,
    fetcher: Fetcher | None = None,
) -> Contexto:
    """Funde contexto do YAML com extras da CLI e resolve as fontes.

    Lê o conteúdo dos arquivos/diretórios de ``docs``, baixa o conteúdo das
    URLs de ``links`` e lê o arquivo ``skill.best_practices`` (se houver).

    Args:
        config: configuração carregada.
        extra_docs: diretórios/arquivos de doc passados via ``--doc`` (estendem o YAML).
        extra_links: URLs passadas via ``--link`` (estendem o YAML).
        fetcher: função opcional para baixar links (injetável em teste);
            quando None, usa HTTP GET real (``_fetch_padrao``).

    Returns:
        Contexto pronto para injeção nos prompts dos agentes.
    """
    docs = [*config.contexto.docs, *(extra_docs or [])]
    links = [*config.contexto.links, *(extra_links or [])]
    fetch = fetcher or _fetch_padrao

    bp_conteudo: str | None = None
    if config.skill.best_practices:
        caminho = Path(config.skill.best_practices)
        if caminho.exists():
            bp_conteudo = caminho.read_text(encoding="utf-8")

    docs_conteudo = _coletar_docs(docs)
    links_conteudo = _coletar_links(links, fetch)
    log.info(
        "contexto_montado",
        docs=len(docs),
        docs_lidos=len(docs_conteudo),
        links=len(links),
        links_baixados=len(links_conteudo),
        best_practices=bp_conteudo is not None,
    )

    return Contexto(
        docs=docs,
        links=links,
        best_practices_conteudo=bp_conteudo,
        docs_conteudo=docs_conteudo,
        links_conteudo=links_conteudo,
    )
