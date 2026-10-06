# Transcritor Local — transcrição e diarização de entrevistas

Aplicação **100% local** que transforma gravações de entrevistas (`.mp4`, `.mkv`, `.mov`, `.avi`) em transcrições
estruturadas: quem falou, o texto, o início e o fim de cada trecho. A identificação dos speakers é revisada por
você, e o resultado é exportado para **DOCX**, **XLSX**, **TXT**, **JSON** e **SRT**.

> 🔒 **Privacidade:** nenhum vídeo, áudio, documento ou transcrição sai do computador. O servidor escuta apenas
> em `127.0.0.1`. A aplicação força `HF_HUB_OFFLINE=1` e desliga a telemetria (`HF_HUB_DISABLE_TELEMETRY`,
> `PYANNOTE_METRICS_ENABLED=0`). A interface não usa CDN nem fontes externas. A internet só é usada uma vez, por
> `baixar_modelos.py`, para **baixar** os pesos dos modelos.

---

## 1. Diagnóstico do computador

Rode antes de instalar qualquer coisa (só usa a biblioteca padrão do Python):

```bash
python diagnostico.py          # relatório
python diagnostico.py --json   # mesmo relatório em JSON
```

Ele mostra o sistema operacional, a CPU, a RAM, a GPU (NVIDIA/AMD/Apple) com a VRAM, e as versões do Python,
do Node.js e do FFmpeg. Também recomenda um dispositivo e um modelo. A interface mostra o mesmo resumo na tela
inicial.

| Componente                | Usa GPU?                                 |
|---------------------------|------------------------------------------|
| FFmpeg (extração de áudio)| Não precisa (é rápido em CPU)            |
| faster-whisper (transcrição) | GPU NVIDIA (CUDA) ou CPU (int8)       |
| pyannote (diarização)     | GPU NVIDIA (CUDA), Apple Silicon (MPS) ou CPU |

Modelo padrão escolhido automaticamente:

| Hardware                         | Modelo Whisper padrão |
|----------------------------------|-----------------------|
| GPU NVIDIA ≥ 10 GB               | `large-v3`            |
| GPU NVIDIA 6–10 GB               | `large-v3-turbo`      |
| GPU NVIDIA 4–6 GB                | `medium`              |
| CPU com ≥ 8 GB RAM e ≥ 4 núcleos | `small`               |
| CPU mais modesta                 | `base`                |

Você pode trocar o modelo na tela de configurações de cada entrevista.

## 2. Instalação

Pré-requisitos: **Python 3.10 ou mais recente**. O FFmpeg é recomendado. Se ele não estiver no `PATH`, a
aplicação usa o binário do pacote `imageio-ffmpeg`. O Node.js **não** é necessário.

```bash
# Linux / macOS
./iniciar.sh          # cria .venv, instala dependências e inicia

# Windows
iniciar.bat
```

Ou manualmente:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**GPU NVIDIA:** o `pip install` traz o PyTorch com CUDA no Linux. No Windows, instale antes o PyTorch com CUDA
(veja https://pytorch.org/get-started/locally/). Para o faster-whisper usar a GPU, ele precisa das bibliotecas
cuBLAS e cuDNN (`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`). Se elas não estiverem presentes, a aplicação
usa a CPU automaticamente.

## 3. Download dos modelos (uma única vez, com internet)

1. Crie uma conta gratuita em https://huggingface.co
2. Aceite os termos de uso de https://huggingface.co/pyannote/speaker-diarization-community-1
3. Crie um token de leitura em https://huggingface.co/settings/tokens
4. Rode:

```bash
python baixar_modelos.py --hf-token hf_SEU_TOKEN                    # Whisper recomendado + diarização
python baixar_modelos.py --whisper small medium                    # outros modelos Whisper
```

Os modelos ficam em `modelos/`. O token é usado só nesse download e não é salvo. Depois disso, a aplicação
funciona **sem internet**: você pode até desconectar o computador da rede para processar.

## 4. Uso

```bash
python -m app        # abre http://127.0.0.1:8765 no navegador
```

1. Selecione o vídeo e, se tiver, o `.docx` com os participantes.
2. Confirme ou corrija os participantes lidos do DOCX. Se nada for reconhecido, digite os nomes.
3. Escolha o modelo, o idioma (Português do Brasil por padrão) e o número de speakers. Informar o número de
   speakers melhora bastante a diarização. Clique em **Confirmar e processar**.
4. Acompanhe o progresso: extração do áudio → transcrição → diarização → combinação.
5. **Associe cada `SPEAKER_XX` a um participante.** Ouça os trechos de exemplo (▶) antes de escolher. A
   identidade nunca é presumida automaticamente.
6. **Revise.** Você pode:
   - editar o texto;
   - trocar a pessoa de um trecho;
   - ajustar início e fim;
   - dividir um trecho no cursor (✂︎);
   - juntar um trecho com o próximo (⤓);
   - excluir um trecho.

   Clicar em `[hh:mm:ss]` leva o player àquele ponto. O player tem velocidades de 0.5x, 1x, 1.5x e 2x, além dos
   atalhos `Ctrl+Espaço` (play/pausa) e `Alt+←/→` (±5 s). Há duas visualizações, **Blocos** e **Tabela**, com
   busca e filtro por pessoa. Trechos com baixa confiança aparecem sublinhados. As alterações são salvas
   automaticamente.
7. **Exporte** para DOCX, XLSX, TXT, JSON ou SRT.

Os projetos ficam em `dados/<id>/`, com o vídeo, o `audio.wav` e o `projeto.json`. Você pode reabri-los na tela
inicial. Excluir um projeto apaga a pasta.

## 5. Arquitetura

```text
Navegador (HTML/CSS/JS puro)  ──HTTP 127.0.0.1──►  FastAPI (Python)
                                                     │
        ┌────────────────────────────────────────────┤ thread de processamento (1 por vez)
        ▼                                            │
  FFmpeg → WAV 16 kHz mono → faster-whisper (palavras + timestamps)
                           → pyannote (turnos de fala por speaker)
                           → combinação palavra×turno → segmentos
                                                     │
              associação de speakers → revisão → exportação (python-docx / openpyxl)
```

| Arquivo | Responsabilidade |
|---|---|
| `diagnostico.py` | Diagnóstico de hardware e software (só biblioteca padrão) |
| `baixar_modelos.py` | Download único dos modelos para `modelos/` |
| `app/main.py` | API FastAPI e arquivos estáticos |
| `app/participantes.py` | Leitura tolerante do DOCX: bloco "Participantes", listas, tabelas e linhas "Nome — Papel" |
| `app/audio.py` | Extração de áudio com FFmpeg |
| `app/transcricao.py` | faster-whisper com timestamps por palavra e filtro VAD |
| `app/diarizacao.py` | pyannote.audio (compatível com as versões 3.x e 4.x) |
| `app/combinacao.py` | Atribui cada palavra ao speaker de maior sobreposição e agrupa em segmentos |
| `app/projeto.py` | Persistência em JSON e execução em segundo plano |
| `app/exportacao.py` | DOCX, XLSX, TXT, JSON e SRT |
| `app/static/` | Interface |

### Por que estas escolhas

- **FastAPI + HTML/JS (em vez de Streamlit):** a revisão precisa de um player de vídeo controlado por código
  (pular para um horário, mudar a velocidade, destacar o trecho em reprodução) e de edição em linha de centenas
  de blocos. No Streamlit, cada interação reexecuta o script inteiro, e controlar o player exige componentes
  customizados. Com FastAPI e JavaScript puro isso é direto e não depende de nada externo: não há build, nem
  Node, nem CDN.
- **faster-whisper:** é a mesma qualidade do Whisper da OpenAI, rodando localmente via CTranslate2. É cerca de 4x
  mais rápido e usa menos memória. Faz quantização int8 eficiente na CPU (importante sem GPU) e usa CUDA quando
  disponível. Dá timestamps por palavra e tem filtro VAD embutido (Silero). Instala com `pip`, sem compilar. O
  Whisper.cpp seria uma alternativa, mas exige compilação e integração mais trabalhosa. O WhisperX acrescenta
  dependências e um modelo de alinhamento extra, o que é desnecessário porque os timestamps por palavra do
  faster-whisper já bastam para a combinação com a diarização.
- **pyannote.audio (`speaker-diarization-community-1`):** é a referência open-source em diarização e roda
  totalmente local (CPU, CUDA ou MPS). Aceita número exato, mínimo ou máximo de speakers. O WhisperX usa o próprio
  pyannote por baixo. O modelo é aberto, mas exige aceitar os termos uma vez para o download.
  - Para usar a versão anterior, defina `TRANSCRITOR_DIARIZACAO=pyannote/speaker-diarization-3.1`.
  - O pacote `pyannoteai-sdk`, instalado como dependência, só é usado com os modelos *pagos em nuvem* da
    pyannoteAI, e a aplicação **não** os utiliza.
- **Idioma explícito:** o padrão é `pt`. Os nomes dos participantes são passados ao Whisper como contexto inicial,
  o que melhora a grafia dos nomes próprios. Isso pode ser desligado em "Avançado".

### Configuração por variáveis de ambiente

| Variável | Padrão | Função |
|---|---|---|
| `TRANSCRITOR_PORTA` | `8765` | porta local |
| `TRANSCRITOR_DADOS` | `./dados` | onde ficam os projetos |
| `TRANSCRITOR_MODELOS` | `./modelos` | onde ficam os modelos |
| `TRANSCRITOR_DIARIZACAO` | `pyannote/speaker-diarization-community-1` | pipeline do pyannote (ID já baixado ou caminho para um `config.yaml`) |

## 6. Desempenho esperado (aproximado, 1 hora de entrevista)

| Configuração | Transcrição | Diarização |
|---|---|---|
| CPU 4–8 núcleos, `small` int8 | 20–60 min | 10–30 min |
| CPU 4–8 núcleos, `medium` int8 | 1–2 h | 10–30 min |
| GPU NVIDIA 8 GB, `large-v3-turbo` | 3–6 min | 1–2 min |

## 7. Testes

```bash
pip install -r requirements-dev.txt
pytest
```

Os testes cobrem a leitura do DOCX em vários formatos, a combinação transcrição + diarização, a conversão de
tempos, o fluxo completo da API (com modelos simulados), as exportações e o suporte a `Range` no player.

## 8. Limitações conhecidas e próximos passos

- A associação dos speakers é manual por decisão de projeto. O reconhecimento de voz por amostras pode vir
  numa versão futura.
- Fala sobreposta é atribuída ao speaker predominante em cada palavra.
- Os navegadores não reproduzem `.avi` e alguns `.mkv`. Nesses casos, o player usa o áudio extraído, e a navegação
  por horário continua funcionando.
- O processamento em andamento não sobrevive ao encerramento do servidor. Basta reprocessar o projeto.
