#!/usr/bin/env bash
# Instala (na primeira vez) e inicia o Transcritor Local.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
  echo
  echo "Dependências instaladas. Agora baixe os modelos (uma única vez):"
  echo "  .venv/bin/python baixar_modelos.py --hf-token SEU_TOKEN"
  echo
fi
exec .venv/bin/python -m app
