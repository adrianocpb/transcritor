"""Extração de áudio com FFmpeg (local)."""
from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

TAXA = 16000


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:  # binário empacotado (útil no Windows quando o FFmpeg não está no PATH)
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise RuntimeError("FFmpeg não encontrado. Instale o FFmpeg ou o pacote imageio-ffmpeg.") from e


def extrair_audio(video: Path, destino: Path) -> Path:
    """Converte qualquer vídeo/áudio para WAV mono 16 kHz PCM 16 bits."""
    cmd = [ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(video), "-vn", "-ac", "1", "-ar", str(TAXA), "-c:a", "pcm_s16le", str(destino)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not destino.exists() or destino.stat().st_size < 1000:
        raise RuntimeError(f"Falha ao extrair áudio: {proc.stderr.strip()[-800:] or 'arquivo sem trilha de áudio?'}")
    return destino


def carregar_wav(caminho: Path) -> np.ndarray:
    """Lê o WAV gerado por extrair_audio como float32 em [-1, 1]."""
    with wave.open(str(caminho), "rb") as w:
        if w.getframerate() != TAXA or w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise RuntimeError("WAV inesperado; extraia novamente o áudio.")
        dados = w.readframes(w.getnframes())
    return np.frombuffer(dados, dtype=np.int16).astype(np.float32) / 32768.0
