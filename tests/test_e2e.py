import json
from pathlib import Path


def test_langgraph_json_aponta_para_o_grafo():
    cfg = json.loads(Path("langgraph.json").read_text(encoding="utf-8"))
    assert "loopforge" in json.dumps(cfg["graphs"])


def test_graph_app_expoe_grafo_compilado(monkeypatch):
    # config.yaml pode usar prefixos (openrouter:/nvidia:) que montam o cliente no
    # build (precisam da chave), diferente dos providers em string que só resolvem
    # no run. O Studio também exige chaves; aqui usamos dummies só pra compilar,
    # cobrindo qualquer provider que o config.yaml esteja usando.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-teste")
    from loopforge.graph_app import graph

    assert hasattr(graph, "ainvoke")
