"""Diarização local com pyannote.audio (compatível com as versões 3.x e 4.x)."""
from __future__ import annotations

import gc
from typing import Callable

import numpy as np

from .config import MODELO_DIARIZACAO

Progresso = Callable[[float, str], None]

ETAPAS = {"segmentation": "Segmentando a fala", "speaker_counting": "Contando speakers",
          "embeddings": "Extraindo impressões de voz", "discrete_diarization": "Agrupando speakers"}


def disponivel() -> tuple[bool, str]:
    try:
        import pyannote.audio  # noqa: F401
    except Exception as e:
        return False, f"pyannote.audio não instalado ({e.__class__.__name__})"
    from huggingface_hub import try_to_load_from_cache
    if MODELO_DIARIZACAO.endswith((".yaml", ".yml")):
        return True, MODELO_DIARIZACAO
    achado = try_to_load_from_cache(MODELO_DIARIZACAO, "config.yaml")
    if isinstance(achado, str):
        return True, MODELO_DIARIZACAO
    return False, f"modelo '{MODELO_DIARIZACAO}' não baixado (execute baixar_modelos.py)"


def diarizar(audio: np.ndarray, dispositivo: str, num_speakers: int | None,
             min_speakers: int | None, max_speakers: int | None,
             progresso: Progresso) -> list[dict]:
    """Retorna turnos [{inicio, fim, speaker}] ordenados por início."""
    import torch
    from pyannote.audio import Pipeline

    progresso(0.0, "Carregando modelo de diarização…")
    try:
        pipeline = Pipeline.from_pretrained(MODELO_DIARIZACAO)
    except Exception as e:
        raise RuntimeError(f"Não foi possível carregar '{MODELO_DIARIZACAO}'. Execute "
                           f"'python baixar_modelos.py --diarizacao --hf-token SEU_TOKEN' uma vez.\n"
                           f"Detalhe: {e}") from e
    if pipeline is None:
        raise RuntimeError("Modelo de diarização indisponível localmente (execute baixar_modelos.py).")
    if dispositivo in ("cuda", "mps"):
        try:
            pipeline.to(torch.device(dispositivo))
        except Exception:
            dispositivo = "cpu"

    def gancho(nome, artefato, file=None, total=None, completed=None):
        rotulo = ETAPAS.get(nome, nome)
        if total and completed is not None:
            frac = completed / total
            peso = {"segmentation": (0.0, 0.3), "embeddings": (0.3, 0.95)}.get(nome, (0.95, 1.0))
            progresso(peso[0] + (peso[1] - peso[0]) * frac, f"{rotulo}… {int(frac * 100)}%")
        else:
            progresso(-1, f"{rotulo}…")

    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = int(num_speakers)
    else:
        if min_speakers:
            kwargs["min_speakers"] = int(min_speakers)
        if max_speakers:
            kwargs["max_speakers"] = int(max_speakers)
    entrada = {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": 16000}
    saida = pipeline(entrada, hook=gancho, **kwargs)
    # pyannote 4.x devolve um objeto com .exclusive_speaker_diarization / .speaker_diarization
    anotacao = saida
    for atributo in ("exclusive_speaker_diarization", "speaker_diarization"):
        if getattr(saida, atributo, None) is not None:
            anotacao = getattr(saida, atributo)
            break
    turnos = [{"inicio": round(t.start, 3), "fim": round(t.end, 3), "speaker": str(rotulo)}
              for t, _, rotulo in anotacao.itertracks(yield_label=True)]
    del pipeline
    gc.collect()
    return renomear_speakers(sorted(turnos, key=lambda t: t["inicio"]))


def renomear_speakers(turnos: list[dict]) -> list[dict]:
    """Renumera SPEAKER_00, SPEAKER_01… pela ordem em que cada voz aparece."""
    mapa: dict[str, str] = {}
    for t in turnos:
        if t["speaker"] not in mapa:
            mapa[t["speaker"]] = f"SPEAKER_{len(mapa):02d}"
        t["speaker"] = mapa[t["speaker"]]
    return turnos
