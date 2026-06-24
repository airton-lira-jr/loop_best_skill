import logging

from loopforge.logging import get_logger, setup_logging


def test_logger_emite_evento(capsys):
    setup_logging()
    log = get_logger("teste")
    log.info("no_avancou", iteracao=1, score=0.5)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "no_avancou" in out


def test_setup_logging_idempotente():
    setup_logging()
    setup_logging(verbose=True)
    assert len(logging.root.handlers) == 1
