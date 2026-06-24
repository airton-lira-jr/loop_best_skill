import json
from pathlib import Path


def test_langgraph_json_aponta_para_o_grafo():
    cfg = json.loads(Path("langgraph.json").read_text(encoding="utf-8"))
    assert "loopforge" in json.dumps(cfg["graphs"])


def test_graph_app_expoe_grafo_compilado():
    from loopforge.graph_app import graph

    assert hasattr(graph, "ainvoke")
