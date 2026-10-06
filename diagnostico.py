#!/usr/bin/env python3
"""Diagnóstico do computador para o Transcritor Local.

Usa apenas a biblioteca padrão do Python, então pode ser executado antes de
instalar qualquer dependência:

    python diagnostico.py          # relatório legível
    python diagnostico.py --json   # saída em JSON

Nada é enviado para a internet: o script apenas lê informações do sistema.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def cpu_info() -> dict:
    nome = platform.processor() or ""
    sistema = platform.system()
    if sistema == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
                for linha in f:
                    if linha.lower().startswith("model name"):
                        nome = linha.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
    elif sistema == "Darwin":
        nome = _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip() or nome
    elif sistema == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor).Name"])
        nome = out.strip().splitlines()[0] if out.strip() else nome
    fisicos = None
    try:
        import multiprocessing
        logicos = multiprocessing.cpu_count()
    except Exception:
        logicos = os.cpu_count()
    if sistema == "Linux":
        out = _run(["lscpu"])
        m_cores = re.search(r"Core\(s\) per socket:\s*(\d+)", out)
        m_sockets = re.search(r"Socket\(s\):\s*(\d+)", out)
        if m_cores and m_sockets:
            fisicos = int(m_cores.group(1)) * int(m_sockets.group(1))
    elif sistema == "Darwin":
        v = _run(["sysctl", "-n", "hw.physicalcpu"]).strip()
        fisicos = int(v) if v.isdigit() else None
    return {"modelo": nome or "desconhecido", "nucleos_logicos": logicos,
            "nucleos_fisicos": fisicos, "arquitetura": platform.machine()}


def ram_gb() -> float | None:
    sistema = platform.system()
    try:
        if sistema == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                for linha in f:
                    if linha.startswith("MemTotal"):
                        return round(int(linha.split()[1]) / 1024 / 1024, 1)
        elif sistema == "Darwin":
            v = _run(["sysctl", "-n", "hw.memsize"]).strip()
            return round(int(v) / 1024 ** 3, 1)
        elif sistema == "Windows":
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMSTAT()
            st.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return round(st.ullTotalPhys / 1024 ** 3, 1)
    except Exception:
        pass
    return None


def gpus() -> list[dict]:
    encontradas: list[dict] = []
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
                    "--format=csv,noheader,nounits"])
        for linha in out.strip().splitlines():
            partes = [p.strip() for p in linha.split(",")]
            if len(partes) >= 3 and partes[1].replace(".", "").isdigit():
                encontradas.append({
                    "fabricante": "NVIDIA", "modelo": partes[0],
                    "vram_total_gb": round(float(partes[1]) / 1024, 1),
                    "vram_livre_gb": round(float(partes[2]) / 1024, 1),
                    "driver": partes[3] if len(partes) > 3 else None,
                    "cuda": True,
                })
    if shutil.which("rocm-smi"):
        out = _run(["rocm-smi", "--showproductname"])
        for linha in out.splitlines():
            if "Card series" in linha or "Card SKU" in linha:
                encontradas.append({"fabricante": "AMD", "modelo": linha.split(":", 1)[-1].strip(),
                                    "cuda": False, "rocm": True})
                break
    sistema = platform.system()
    if sistema == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"], timeout=20)
        for m in re.finditer(r"Chipset Model:\s*(.+)", out):
            encontradas.append({"fabricante": "Apple/Intel/AMD", "modelo": m.group(1).strip(),
                                "cuda": False, "mps": platform.machine() == "arm64"})
    elif sistema == "Windows" and not encontradas:
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }"])
        for linha in out.strip().splitlines():
            if linha.strip():
                encontradas.append({"fabricante": linha.split()[0], "modelo": linha.strip(), "cuda": False})
    elif sistema == "Linux" and not encontradas and shutil.which("lspci"):
        out = _run(["lspci"])
        for linha in out.splitlines():
            if re.search(r"VGA|3D controller", linha):
                encontradas.append({"fabricante": "?", "modelo": linha.split(":", 2)[-1].strip(), "cuda": False})
    return encontradas


def ferramenta(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    out = _run(cmd).strip().splitlines()
    return out[0] if out else "instalado"


def bibliotecas_python() -> dict:
    """Verifica bibliotecas já instaladas (se existirem) e o suporte a GPU delas."""
    resultado: dict = {}
    try:
        import torch  # type: ignore
        resultado["torch"] = {
            "versao": torch.__version__,
            "cuda_disponivel": bool(torch.cuda.is_available()),
            "mps_disponivel": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
        }
    except Exception:
        resultado["torch"] = None
    try:
        import ctranslate2  # type: ignore
        resultado["ctranslate2"] = {"versao": ctranslate2.__version__,
                                    "gpus_cuda": ctranslate2.get_cuda_device_count()}
    except Exception:
        resultado["ctranslate2"] = None
    for nome in ("faster_whisper", "pyannote.audio", "fastapi", "docx", "openpyxl"):
        try:
            mod = __import__(nome, fromlist=["__version__"])
            resultado[nome] = getattr(mod, "__version__", "instalado")
        except Exception:
            resultado[nome] = None
    return resultado


def recomendacao(ram: float | None, cpu: dict, lista_gpus: list[dict]) -> dict:
    nvidia = [g for g in lista_gpus if g.get("cuda")]
    if nvidia:
        vram = max(g.get("vram_total_gb") or 0 for g in nvidia)
        if vram >= 10:
            modelo = "large-v3"
        elif vram >= 6:
            modelo = "large-v3-turbo"
        elif vram >= 4:
            modelo = "medium"
        else:
            modelo = "small"
        return {"dispositivo": "cuda", "modelo_whisper": modelo,
                "comentario": f"GPU NVIDIA com {vram} GB: transcrição e diarização na GPU."}
    nucleos = cpu.get("nucleos_fisicos") or cpu.get("nucleos_logicos") or 2
    ram = ram or 4
    if ram >= 12 and nucleos >= 8:
        modelo = "small"
        comentario = "Sem GPU NVIDIA: CPU com int8. 'small' equilibra qualidade e velocidade; 'medium' é viável se houver tempo."
    elif ram >= 8 and nucleos >= 4:
        modelo = "small"
        comentario = "Sem GPU NVIDIA: CPU com int8. 'small' é o melhor equilíbrio; espere ~0,5–1x a duração do áudio."
    else:
        modelo = "base"
        comentario = "Hardware modesto: 'base' para manter o tempo de processamento aceitável."
    apple = any(g.get("mps") for g in lista_gpus)
    if apple:
        comentario += " Apple Silicon: a diarização (pyannote) pode usar MPS; a transcrição roda na CPU."
    return {"dispositivo": "cpu", "modelo_whisper": modelo, "comentario": comentario}


def coletar() -> dict:
    cpu = cpu_info()
    ram = ram_gb()
    lista_gpus = gpus()
    return {
        "sistema_operacional": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": cpu,
        "ram_gb": ram,
        "gpus": lista_gpus,
        "python": {"versao": platform.python_version(), "executavel": sys.executable},
        "node": ferramenta(["node", "--version"]),
        "ffmpeg": ferramenta(["ffmpeg", "-version"]),
        "bibliotecas": bibliotecas_python(),
        "recomendacao": recomendacao(ram, cpu, lista_gpus),
    }


def imprimir(d: dict) -> None:
    print("=" * 64)
    print(" DIAGNÓSTICO — Transcritor Local")
    print("=" * 64)
    print(f"Sistema operacional : {d['sistema_operacional']}")
    c = d["cpu"]
    print(f"CPU                 : {c['modelo']} ({c['arquitetura']})")
    print(f"Núcleos             : {c['nucleos_fisicos'] or '?'} físicos / {c['nucleos_logicos']} lógicos")
    print(f"Memória RAM         : {d['ram_gb'] or '?'} GB")
    if d["gpus"]:
        for g in d["gpus"]:
            vram = f" — {g['vram_total_gb']} GB VRAM ({g.get('vram_livre_gb')} GB livres)" if g.get("vram_total_gb") else ""
            print(f"GPU                 : {g['fabricante']} {g['modelo']}{vram}")
    else:
        print("GPU                 : nenhuma GPU detectada")
    print(f"Python              : {d['python']['versao']} ({d['python']['executavel']})")
    print(f"Node.js             : {d['node'] or 'não instalado (não é necessário)'}")
    print(f"FFmpeg              : {d['ffmpeg'] or 'NÃO ENCONTRADO no PATH'}")
    print("-" * 64)
    print("Bibliotecas Python já instaladas:")
    for k, v in d["bibliotecas"].items():
        print(f"  {k:<16}: {v if v else '—'}")
    print("-" * 64)
    print("Uso de GPU por componente:")
    print("  FFmpeg (extração de áudio) : CPU (rápido, não precisa de GPU)")
    print("  faster-whisper (transcrição): GPU NVIDIA/CUDA ou CPU (int8)")
    print("  pyannote (diarização)      : GPU NVIDIA/CUDA, Apple MPS ou CPU")
    print("-" * 64)
    r = d["recomendacao"]
    print(f"Recomendação: dispositivo={r['dispositivo']}  modelo={r['modelo_whisper']}")
    print(f"  {r['comentario']}")
    print("=" * 64)


if __name__ == "__main__":
    dados = coletar()
    if "--json" in sys.argv:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
    else:
        imprimir(dados)
