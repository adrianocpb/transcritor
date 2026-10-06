"""Transcrição local com faster-whisper (CTranslate2)."""
from __future__ import annotations

import gc
from typing import Callable

import numpy as np

from .config import DIR_WHISPER

Progresso = Callable[[float, str], None]


def modelos_baixados() -> list[str]:
    """Lista modelos presentes em modelos/whisper (cache da Hugging Face)."""
    nomes = []
    for d in DIR_WHISPER.glob("models--*"):
        if any(d.glob("snapshots/*/model.bin")):
            nomes.append(d.name.split("--")[-1].replace("faster-whisper-", ""))
    return sorted(nomes)


def transcrever(audio: np.ndarray, modelo: str, idioma: str | None, dispositivo: str,
                threads: int, prompt: str | None, progresso: Progresso) -> tuple[list[dict], dict]:
    """Retorna (palavras, info). Cada palavra: {inicio, fim, texto, prob}."""
    from faster_whisper import WhisperModel

    if dispositivo == "cuda":
        tipos = ["float16", "int8_float16", "int8"]
    else:
        dispositivo, tipos = "cpu", ["int8", "float32"]
    progresso(0.0, f"Carregando modelo '{modelo}' ({dispositivo})…")
    ultimo_erro: Exception | None = None
    whisper = None
    for tipo in tipos:
        try:
            whisper = WhisperModel(modelo, device=dispositivo, compute_type=tipo,
                                   cpu_threads=threads, download_root=str(DIR_WHISPER),
                                   local_files_only=True)
            break
        except Exception as e:  # tipo de computação não suportado ou modelo ausente
            ultimo_erro = e
            if "local_files_only" in str(e) or "snapshot" in str(e).lower() or "not found" in str(e).lower():
                break
    if whisper is None:
        raise RuntimeError(
            f"Não foi possível carregar o modelo '{modelo}'. Ele foi baixado? "
            f"Execute: python baixar_modelos.py --whisper {modelo}\nDetalhe: {ultimo_erro}")

    duracao = len(audio) / 16000
    segmentos, info = whisper.transcribe(
        audio, language=idioma or None, task="transcribe", beam_size=5,
        word_timestamps=True, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False, initial_prompt=prompt or None)
    progresso(0.0, f"Transcrevendo (idioma: {info.language})…")
    palavras: list[dict] = []
    for seg in segmentos:
        if seg.words:
            for w in seg.words:
                palavras.append({"inicio": round(w.start, 3), "fim": round(w.end, 3),
                                 "texto": w.word, "prob": round(w.probability, 3)})
        elif seg.text.strip():
            palavras.append({"inicio": round(seg.start, 3), "fim": round(seg.end, 3),
                             "texto": " " + seg.text.strip(), "prob": 1.0})
        progresso(min(1.0, seg.end / duracao) if duracao else 1.0,
                  f"Transcrevendo… {int(seg.end // 60)}:{int(seg.end % 60):02d} de "
                  f"{int(duracao // 60)}:{int(duracao % 60):02d}")
    del whisper
    gc.collect()
    return palavras, {"idioma_detectado": info.language, "prob_idioma": round(info.language_probability, 3),
                      "duracao": duracao}
