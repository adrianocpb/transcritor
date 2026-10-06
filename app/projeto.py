"""Armazenamento de projetos (pasta dados/<id>/) e execução do processamento."""
from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import audio as audio_mod
from . import combinacao
from .config import DIR_DADOS

_trava = threading.RLock()
_executor = ThreadPoolExecutor(max_workers=1)  # um processamento pesado por vez

DESCONHECIDO = "Outro / desconhecido"


def pasta(pid: str) -> Path:
    if not pid or not all(c.isalnum() or c == "-" for c in pid):
        raise KeyError(pid)
    return DIR_DADOS / pid


def carregar(pid: str) -> dict:
    arq = pasta(pid) / "projeto.json"
    if not arq.exists():
        raise KeyError(pid)
    with _trava:
        return json.loads(arq.read_text(encoding="utf-8"))


def salvar(proj: dict) -> dict:
    proj["atualizado_em"] = time.strftime("%Y-%m-%d %H:%M:%S")
    arq = pasta(proj["id"]) / "projeto.json"
    with _trava:
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(arq)
    return proj


def atualizar(pid: str, **campos) -> dict:
    with _trava:
        proj = carregar(pid)
        proj.update(campos)
        return salvar(proj)


def criar(nome_video: str) -> dict:
    pid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    pasta(pid).mkdir(parents=True)
    proj = {
        "id": pid, "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "arquivo_video": nome_video, "video": None, "entrevista": "", "participantes": [],
        "status": "novo", "progresso": 0.0, "mensagem": "", "erro": None,
        "config": {}, "info": {}, "speakers": {}, "segmentos": [],
    }
    return salvar(proj)


def listar() -> list[dict]:
    itens = []
    for arq in sorted(DIR_DADOS.glob("*/projeto.json"), reverse=True):
        try:
            p = json.loads(arq.read_text(encoding="utf-8"))
            itens.append({k: p.get(k) for k in ("id", "criado_em", "atualizado_em", "arquivo_video",
                                                 "entrevista", "status")})
        except Exception:
            continue
    return itens


def excluir(pid: str) -> None:
    shutil.rmtree(pasta(pid), ignore_errors=True)


def marcar_interrompidos() -> None:
    """Processamentos em andamento quando o servidor foi encerrado não continuam sozinhos."""
    for arq in DIR_DADOS.glob("*/projeto.json"):
        try:
            p = json.loads(arq.read_text(encoding="utf-8"))
            if p.get("status") in ("na_fila", "processando"):
                p.update(status="erro", erro="Processamento interrompido (servidor reiniciado).")
                salvar(p)
        except Exception:
            continue


def nome_exibicao(proj: dict, seg: dict) -> str:
    if seg.get("pessoa"):
        return seg["pessoa"]
    mapeado = proj.get("speakers", {}).get(seg.get("speaker", ""))
    return mapeado or seg.get("speaker") or "?"


# ---------------------------------------------------------------- processamento

def iniciar(pid: str, config: dict) -> None:
    atualizar(pid, status="na_fila", progresso=0.0, mensagem="Aguardando na fila…", erro=None, config=config)
    _executor.submit(_processar, pid, config)


def _processar(pid: str, cfg: dict) -> None:
    inicio_total = time.time()
    estado = {"ultimo": 0.0}

    def etapa(ini: float, fim: float):
        def progresso(frac: float, msg: str):
            agora = time.time()
            if frac >= 0:
                p = ini + (fim - ini) * max(0.0, min(1.0, frac))
            else:
                p = None
            if agora - estado["ultimo"] < 0.5 and frac not in (0.0, 1.0):
                return
            estado["ultimo"] = agora
            campos = {"mensagem": msg}
            if p is not None:
                campos["progresso"] = round(p, 4)
            atualizar(pid, **campos)
        return progresso

    try:
        proj = atualizar(pid, status="processando", progresso=0.0, mensagem="Extraindo áudio…")
        dir_p = pasta(pid)
        wav = dir_p / "audio.wav"
        tempos = {}
        t = time.time()
        if not wav.exists():
            audio_mod.extrair_audio(dir_p / proj["video"], wav)
        sinal = audio_mod.carregar_wav(wav)
        tempos["extracao_audio"] = round(time.time() - t, 1)

        com_diar = bool(cfg.get("diarizar", True))
        fim_trans = 0.6 if com_diar else 0.95
        prompt = None
        nomes = [p["nome"] for p in proj.get("participantes", []) if p.get("nome")]
        if nomes and cfg.get("usar_nomes_no_prompt", True):
            prompt = "Entrevista com " + ", ".join(nomes) + "."

        from . import transcricao
        t = time.time()
        palavras, info = transcricao.transcrever(
            sinal, cfg["modelo"], cfg.get("idioma") or None, cfg.get("dispositivo_transcricao", "cpu"),
            cfg.get("threads", 4), prompt, etapa(0.05, fim_trans))
        tempos["transcricao"] = round(time.time() - t, 1)
        (dir_p / "palavras.json").write_text(json.dumps(palavras, ensure_ascii=False), encoding="utf-8")

        turnos: list[dict] = []
        if com_diar:
            from . import diarizacao
            t = time.time()
            turnos = diarizacao.diarizar(sinal, cfg.get("dispositivo_diarizacao", "cpu"),
                                         cfg.get("num_speakers"), cfg.get("min_speakers"),
                                         cfg.get("max_speakers"), etapa(fim_trans, 0.97))
            tempos["diarizacao"] = round(time.time() - t, 1)
            (dir_p / "diarizacao.json").write_text(json.dumps(turnos, ensure_ascii=False), encoding="utf-8")

        atualizar(pid, progresso=0.98, mensagem="Combinando transcrição e diarização…")
        segmentos = combinacao.montar_segmentos(palavras, turnos)
        speakers = sorted({s["speaker"] for s in segmentos})
        tempos["total"] = round(time.time() - inicio_total, 1)
        info.update(tempos=tempos, num_speakers=len(speakers), diarizacao=com_diar)
        atualizar(pid, status="mapear_speakers", progresso=1.0, mensagem="Concluído.",
                  segmentos=segmentos, speakers={s: "" for s in speakers}, info=info)
    except Exception as e:
        traceback.print_exc()
        atualizar(pid, status="erro", erro=str(e), mensagem="Falha no processamento.")
