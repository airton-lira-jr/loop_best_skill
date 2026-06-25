import os

from loopforge.env import carregar_env


def test_carrega_variaveis_do_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LOOPFORGE_TESTVAR=abc123\n", encoding="utf-8")
    monkeypatch.delenv("LOOPFORGE_TESTVAR", raising=False)

    carregar_env(env)

    assert os.environ["LOOPFORGE_TESTVAR"] == "abc123"


def test_nao_sobrescreve_env_existente(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LOOPFORGE_TESTVAR=do_arquivo\n", encoding="utf-8")
    monkeypatch.setenv("LOOPFORGE_TESTVAR", "ja_definido")

    carregar_env(env)

    # env já exportado vence o .env (não sobrescreve).
    assert os.environ["LOOPFORGE_TESTVAR"] == "ja_definido"


def test_arquivo_ausente_nao_quebra(tmp_path):
    carregar_env(tmp_path / "nao_existe.env")  # não deve levantar
