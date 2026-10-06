import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="transcritor-teste-")
os.environ["TRANSCRITOR_DADOS"] = str(Path(_tmp) / "dados")
os.environ["TRANSCRITOR_MODELOS"] = str(Path(_tmp) / "modelos")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
