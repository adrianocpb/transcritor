"""Caminhos e variáveis de ambiente.

Este módulo é importado antes de qualquer biblioteca da Hugging Face/pyannote
para garantir que o modo offline e a ausência de telemetria estejam ativos.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_MODELOS = Path(os.environ.get("TRANSCRITOR_MODELOS", RAIZ / "modelos"))
DIR_WHISPER = DIR_MODELOS / "whisper"
DIR_HF = DIR_MODELOS / "huggingface"
DIR_DADOS = Path(os.environ.get("TRANSCRITOR_DADOS", RAIZ / "dados"))

# Modelo de diarização (repositório do Hugging Face já baixado em DIR_HF ou
# caminho local para um config.yaml do pyannote).
MODELO_DIARIZACAO = os.environ.get("TRANSCRITOR_DIARIZACAO", "pyannote/speaker-diarization-community-1")

MODELOS_WHISPER = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]

HOST = os.environ.get("TRANSCRITOR_HOST", "127.0.0.1")
PORTA = int(os.environ.get("TRANSCRITOR_PORTA", "8765"))


def ativar_modo_offline(offline: bool = True) -> None:
    """Configura o ambiente para nunca enviar dados para fora do computador."""
    os.environ["HF_HOME"] = str(DIR_HF)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1" if offline else "0"
    os.environ["TRANSFORMERS_OFFLINE"] = "1" if offline else "0"


for _d in (DIR_WHISPER, DIR_HF, DIR_DADOS):
    _d.mkdir(parents=True, exist_ok=True)
