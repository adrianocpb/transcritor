"""Detecção de hardware em tempo de execução e escolha de padrões."""
from __future__ import annotations

import functools
import os
import sys

from .config import RAIZ

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
import diagnostico  # noqa: E402  (script de diagnóstico na raiz do projeto)


def _cuda_ctranslate2() -> int:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def _torch_dispositivo() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


@functools.lru_cache(maxsize=1)
def detectar() -> dict:
    cpu = diagnostico.cpu_info()
    ram = diagnostico.ram_gb()
    gpus = diagnostico.gpus()
    rec = diagnostico.recomendacao(ram, cpu, gpus)
    cuda_ct2 = _cuda_ctranslate2()
    disp_torch = _torch_dispositivo()
    # O que o software instalado realmente consegue usar:
    disp_transcricao = "cuda" if cuda_ct2 > 0 else "cpu"
    modelo = rec["modelo_whisper"]
    if disp_transcricao == "cpu" and rec["dispositivo"] == "cuda":
        # Há GPU, mas o CTranslate2/CUDA não está funcional: voltar ao padrão de CPU.
        modelo = "small"
    return {
        "sistema": diagnostico.platform.system(),
        "cpu": cpu,
        "ram_gb": ram,
        "gpus": gpus,
        "dispositivo_transcricao": disp_transcricao,
        "dispositivo_diarizacao": disp_torch,
        "modelo_padrao": modelo,
        "comentario": rec["comentario"],
        "threads": cpu.get("nucleos_fisicos") or os.cpu_count() or 4,
    }
