"""Ponto de entrada do grafo para o LangGraph Studio (`langgraph dev`)."""

from __future__ import annotations

from pathlib import Path

from loopforge.config import load_config
from loopforge.graph import build_graph

_config_path = "config.yaml" if Path("config.yaml").exists() else "config.example.yaml"
graph = build_graph(load_config(_config_path))
