from app import tempo
from app.combinacao import montar_segmentos


def w(i, f, t):
    return {"inicio": i, "fim": f, "texto": " " + t, "prob": 0.9}


def test_alternancia_de_speakers():
    palavras = [w(0.0, 0.4, "Bom"), w(0.5, 0.9, "dia."), w(1.0, 1.5, "Como"), w(1.6, 2.0, "funciona?"),
                w(3.0, 3.4, "Hoje"), w(3.5, 3.9, "funciona"), w(4.0, 4.5, "assim."),
                w(5.0, 5.5, "Entendi.")]
    turnos = [{"inicio": 0.0, "fim": 2.1, "speaker": "SPEAKER_00"},
              {"inicio": 2.9, "fim": 4.6, "speaker": "SPEAKER_01"},
              {"inicio": 4.9, "fim": 5.6, "speaker": "SPEAKER_00"}]
    segs = montar_segmentos(palavras, turnos)
    assert [(s["speaker"], s["texto"]) for s in segs] == [
        ("SPEAKER_00", "Bom dia. Como funciona?"),
        ("SPEAKER_01", "Hoje funciona assim."),
        ("SPEAKER_00", "Entendi."),
    ]
    assert segs[1]["inicio"] == 3.0 and segs[1]["fim"] == 4.5


def test_ilha_de_uma_palavra_e_suavizada():
    palavras = [w(0.0, 0.3, "eu"), w(0.35, 0.6, "acho"), w(0.62, 0.8, "que"), w(0.85, 1.2, "sim.")]
    turnos = [{"inicio": 0.0, "fim": 0.61, "speaker": "SPEAKER_00"},
              {"inicio": 0.61, "fim": 0.81, "speaker": "SPEAKER_01"},
              {"inicio": 0.81, "fim": 1.3, "speaker": "SPEAKER_00"}]
    segs = montar_segmentos(palavras, turnos)
    assert len(segs) == 1 and segs[0]["texto"] == "eu acho que sim."


def test_palavra_fora_de_turno_vai_para_o_mais_proximo():
    palavras = [w(0.0, 0.5, "Olá."), w(10.0, 10.5, "Oi.")]
    turnos = [{"inicio": 0.0, "fim": 0.4, "speaker": "SPEAKER_00"},
              {"inicio": 10.6, "fim": 12.0, "speaker": "SPEAKER_01"}]
    assert [s["speaker"] for s in montar_segmentos(palavras, turnos)] == ["SPEAKER_00", "SPEAKER_01"]


def test_sem_diarizacao_quebra_por_pausa():
    palavras = [w(0, 0.5, "Um."), w(5, 5.5, "Dois.")]
    segs = montar_segmentos(palavras, [])
    assert len(segs) == 2 and all(s["speaker"] == "SPEAKER_00" for s in segs)


def test_tempo():
    assert tempo.formatar(3725.4) == "01:02:05"
    assert tempo.formatar(3725.46, decimos=True) == "01:02:05.5"
    assert tempo.interpretar("01:02:05.5") == 3725.5
    assert tempo.interpretar("2:05") == 125
    assert tempo.formatar_srt(1.234) == "00:00:01,234"
