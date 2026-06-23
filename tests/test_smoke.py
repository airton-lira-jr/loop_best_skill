def test_pacote_importa_e_tem_versao():
    import loopforge

    assert isinstance(loopforge.__version__, str)
    assert loopforge.__version__
