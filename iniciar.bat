@echo off
REM Instala (na primeira vez) e inicia o Transcritor Local.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
  echo.
  echo Dependencias instaladas. Agora baixe os modelos ^(uma unica vez^):
  echo   .venv\Scripts\python baixar_modelos.py --hf-token SEU_TOKEN
  echo.
  pause
)
.venv\Scripts\python -m app
pause
