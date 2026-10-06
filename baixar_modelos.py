#!/usr/bin/env python3
"""Baixa os modelos UMA vez para a pasta modelos/ do projeto.

Esta é a ÚNICA etapa que usa a internet, e ela apenas BAIXA pesos de modelos
(nenhum áudio, vídeo ou documento é enviado). Depois disso, a aplicação roda
com HF_HUB_OFFLINE=1 e não faz nenhuma conexão externa.

Exemplos:
    python baixar_modelos.py                          # modelo Whisper recomendado + diarização
    python baixar_modelos.py --whisper small medium   # escolher modelos Whisper
    python baixar_modelos.py --diarizacao --hf-token hf_xxx

Diarização (pyannote): os modelos são gratuitos, mas exigem aceitar os termos
de uso no site da Hugging Face e um token de leitura:
    1. Crie uma conta em https://huggingface.co
    2. Aceite os termos em https://huggingface.co/pyannote/speaker-diarization-community-1
    3. Crie um token (Read) em https://huggingface.co/settings/tokens
O token é usado só para o download e não é salvo pelo Transcritor.
"""
from __future__ import annotations

import argparse
import os
import sys

from app.config import DIR_WHISPER, MODELO_DIARIZACAO, MODELOS_WHISPER, ativar_modo_offline

ativar_modo_offline(False)  # permite downloads apenas neste script


def baixar_whisper(nome: str) -> None:
    from faster_whisper.utils import download_model
    print(f"→ Baixando Whisper '{nome}' para {DIR_WHISPER} …")
    caminho = download_model(nome, cache_dir=str(DIR_WHISPER))
    print(f"  ok: {caminho}")


def baixar_diarizacao(token: str | None) -> bool:
    print(f"→ Baixando modelo de diarização '{MODELO_DIARIZACAO}' …")
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        print("  pyannote.audio não está instalado (pip install -r requirements.txt).")
        return False
    try:
        try:
            pipeline = Pipeline.from_pretrained(MODELO_DIARIZACAO, token=token)
        except TypeError:  # pyannote 3.x
            pipeline = Pipeline.from_pretrained(MODELO_DIARIZACAO, use_auth_token=token)
    except Exception as e:
        pipeline = None
        print(f"  erro: {e}")
    if pipeline is None:
        print("  Falhou. Verifique se aceitou os termos do modelo no site da Hugging Face\n"
              "  e se o token (--hf-token ou variável HF_TOKEN) está correto.")
        return False
    print("  ok: modelo de diarização disponível offline.")
    return True


def main() -> int:
    import app.hardware as hw
    padrao = hw.detectar()["modelo_padrao"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--whisper", nargs="*", choices=MODELOS_WHISPER,
                    help=f"modelos Whisper a baixar (padrão: {padrao})")
    ap.add_argument("--diarizacao", action="store_true", help="baixar apenas o modelo de diarização")
    ap.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"), help="token da Hugging Face (ou variável HF_TOKEN)")
    args = ap.parse_args()

    so_diar = args.diarizacao and args.whisper is None
    ok = True
    if not so_diar:
        for nome in (args.whisper or [padrao]):
            baixar_whisper(nome)
    if args.diarizacao or args.whisper is None:
        if not args.hf_token:
            print("\n⚠ Sem --hf-token: tentando baixar a diarização sem autenticação (pode falhar).")
        ok = baixar_diarizacao(args.hf_token)
    print("\nPronto. Inicie a aplicação com: python -m app" if ok else
          "\nWhisper pronto; a diarização ainda precisa ser baixada (veja as instruções acima).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
