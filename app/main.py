"""API local (FastAPI) + interface web estática.

Execute com:  python -m app
O servidor escuta apenas em 127.0.0.1 — não fica acessível por outros computadores.
"""
from __future__ import annotations

from .config import ativar_modo_offline

ativar_modo_offline()  # antes de importar qualquer biblioteca da Hugging Face

import re  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
import shutil  # noqa: E402
import unicodedata  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional  # noqa: E402

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import exportacao, hardware, participantes, projeto  # noqa: E402
from .config import MODELO_DIARIZACAO, MODELOS_WHISPER  # noqa: E402

EXT_VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".ogg", ".flac"}
ESTATICO = Path(__file__).parent / "static"



@asynccontextmanager
async def _ciclo_de_vida(_app):
    projeto.marcar_interrompidos()
    yield


app = FastAPI(title="Transcritor Local", docs_url=None, redoc_url=None, lifespan=_ciclo_de_vida)


def _proj(pid: str) -> dict:
    try:
        return projeto.carregar(pid)
    except KeyError:
        raise HTTPException(404, "Projeto não encontrado")


def _salvar_upload(arquivo: UploadFile, destino: Path) -> None:
    with destino.open("wb") as f:
        shutil.copyfileobj(arquivo.file, f, length=8 * 1024 * 1024)


def _nome_arquivo(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^\w.-]+", "_", t).strip("_") or "transcricao"


# ------------------------------------------------------------------ sistema

@app.get("/api/sistema")
def sistema() -> dict:
    from . import diarizacao, transcricao
    hw = hardware.detectar()
    ok_diar, msg_diar = diarizacao.disponivel()
    return {
        "hardware": hw,
        "modelos_whisper": MODELOS_WHISPER,
        "modelos_baixados": transcricao.modelos_baixados(),
        "diarizacao": {"disponivel": ok_diar, "detalhe": msg_diar, "modelo": MODELO_DIARIZACAO},
    }


# ------------------------------------------------------------------ projetos

@app.get("/api/projetos")
def listar() -> list[dict]:
    return projeto.listar()


@app.post("/api/projetos")
def criar(video: UploadFile = File(...), docx: Optional[UploadFile] = File(None)) -> dict:
    ext = Path(video.filename or "").suffix.lower()
    if ext not in EXT_VIDEO:
        raise HTTPException(400, f"Formato não suportado: {ext or '?'}")
    proj = projeto.criar(video.filename or f"video{ext}")
    dir_p = projeto.pasta(proj["id"])
    _salvar_upload(video, dir_p / f"video{ext}")
    proj["video"] = f"video{ext}"
    leitura = {"entrevista": "", "participantes": [], "texto": ""}
    if docx is not None and docx.filename:
        if not docx.filename.lower().endswith(".docx"):
            raise HTTPException(400, "O arquivo de participantes deve ser .docx")
        _salvar_upload(docx, dir_p / "participantes.docx")
        try:
            leitura = participantes.extrair(dir_p / "participantes.docx")
        except Exception as e:
            leitura["texto"] = f"(não foi possível ler o DOCX: {e})"
    proj.update(entrevista=leitura["entrevista"] or Path(video.filename or "").stem,
                participantes=leitura["participantes"], texto_docx=leitura["texto"],
                status="confirmar_participantes")
    return projeto.salvar(proj)


@app.get("/api/projetos/{pid}")
def obter(pid: str) -> dict:
    return _proj(pid)


@app.delete("/api/projetos/{pid}")
def excluir(pid: str) -> dict:
    p = _proj(pid)
    if p["status"] in ("na_fila", "processando"):
        raise HTTPException(409, "Aguarde o fim do processamento.")
    projeto.excluir(pid)
    return {"ok": True}


class Participante(BaseModel):
    nome: str
    papel: str = ""


class DadosParticipantes(BaseModel):
    entrevista: str = ""
    participantes: list[Participante]


@app.put("/api/projetos/{pid}/participantes")
def definir_participantes(pid: str, dados: DadosParticipantes) -> dict:
    _proj(pid)
    lista = [p.model_dump() for p in dados.participantes if p.nome.strip()]
    for p in lista:
        p["nome"] = p["nome"].strip()
        p["papel"] = p["papel"].strip()
    return projeto.atualizar(pid, entrevista=dados.entrevista.strip(), participantes=lista)


class ConfigProcessamento(BaseModel):
    modelo: str = "small"
    idioma: Optional[str] = "pt"
    dispositivo_transcricao: str = "cpu"
    dispositivo_diarizacao: str = "cpu"
    diarizar: bool = True
    num_speakers: Optional[int] = Field(None, ge=1, le=20)
    min_speakers: Optional[int] = Field(None, ge=1, le=20)
    max_speakers: Optional[int] = Field(None, ge=1, le=20)
    usar_nomes_no_prompt: bool = True


@app.post("/api/projetos/{pid}/processar")
def processar(pid: str, cfg: ConfigProcessamento) -> dict:
    p = _proj(pid)
    if p["status"] in ("na_fila", "processando"):
        raise HTTPException(409, "Já está em processamento.")
    if cfg.modelo not in MODELOS_WHISPER:
        raise HTTPException(400, "Modelo inválido")
    dados = cfg.model_dump()
    dados["threads"] = hardware.detectar()["threads"]
    if dados["idioma"] in ("", "auto"):
        dados["idioma"] = None
    projeto.iniciar(pid, dados)
    return _proj(pid)


class Mapeamento(BaseModel):
    speakers: dict[str, str]


@app.put("/api/projetos/{pid}/speakers")
def mapear(pid: str, dados: Mapeamento) -> dict:
    _proj(pid)
    return projeto.atualizar(pid, speakers=dados.speakers, status="revisao")


class Segmento(BaseModel):
    inicio: float
    fim: float
    speaker: str = ""
    pessoa: Optional[str] = None
    texto: str = ""
    confianca: Optional[float] = None


class Segmentos(BaseModel):
    segmentos: list[Segmento]


@app.put("/api/projetos/{pid}/segmentos")
def salvar_segmentos(pid: str, dados: Segmentos) -> dict:
    _proj(pid)
    segs = []
    for i, s in enumerate(sorted(dados.segmentos, key=lambda s: s.inicio), 1):
        d = s.model_dump()
        d["id"] = i
        d["inicio"] = round(max(0.0, d["inicio"]), 2)
        d["fim"] = round(max(d["inicio"], d["fim"]), 2)
        segs.append(d)
    proj = projeto.atualizar(pid, segmentos=segs)
    return {"ok": True, "atualizado_em": proj["atualizado_em"], "segmentos": segs}


# ------------------------------------------------------------------ mídia e exportação

@app.get("/api/projetos/{pid}/midia")
def midia(pid: str, tipo: str = "video"):
    p = _proj(pid)
    dir_p = projeto.pasta(pid)
    if tipo == "audio":
        arq = dir_p / "audio.wav"
    else:
        arq = dir_p / (p.get("video") or "")
    if not arq.is_file():
        raise HTTPException(404, "Mídia não encontrada")
    return FileResponse(arq)  # suporta requisições Range (avançar no player)


@app.get("/api/projetos/{pid}/exportar/{formato}")
def exportar(pid: str, formato: str):
    if formato not in exportacao.FORMATOS:
        raise HTTPException(400, "Formato inválido")
    p = _proj(pid)
    func, mime = exportacao.FORMATOS[formato]
    nome = _nome_arquivo(f"Transcricao_{p.get('entrevista') or Path(p['arquivo_video']).stem}") + f".{formato}"
    return Response(func(p), media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


app.mount("/", StaticFiles(directory=ESTATICO, html=True), name="estatico")
