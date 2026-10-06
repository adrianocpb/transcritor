"""Combina palavras da transcrição com os turnos da diarização em segmentos."""
from __future__ import annotations

import bisect

PAUSA_MAX = 1.5        # segundos de silêncio que forçam novo segmento
DURACAO_ALVO = 25.0    # após isso, quebra no próximo fim de frase
DURACAO_MAX = 60.0     # quebra mesmo sem pontuação
FIM_FRASE = (".", "?", "!", "…")


def atribuir_speakers(palavras: list[dict], turnos: list[dict]) -> list[str]:
    """Para cada palavra, o speaker com maior sobreposição (ou o turno mais próximo)."""
    if not turnos:
        return ["SPEAKER_00"] * len(palavras)
    inicios = [t["inicio"] for t in turnos]
    resultado = []
    for w in palavras:
        a, b = w["inicio"], max(w["fim"], w["inicio"] + 0.01)
        # turnos que podem sobrepor: começam antes do fim da palavra
        j = bisect.bisect_right(inicios, b)
        sobreposicao: dict[str, float] = {}
        k = j - 1
        while k >= 0 and k >= j - 50:  # turnos longos podem começar bem antes
            t = turnos[k]
            ov = min(b, t["fim"]) - max(a, t["inicio"])
            if ov > 0:
                sobreposicao[t["speaker"]] = sobreposicao.get(t["speaker"], 0) + ov
            k -= 1
        if sobreposicao:
            resultado.append(max(sobreposicao, key=sobreposicao.get))
            continue
        meio = (a + b) / 2
        vizinhos = [turnos[i] for i in (j - 1, j) if 0 <= i < len(turnos)]
        mais_proximo = min(vizinhos, key=lambda t: min(abs(meio - t["inicio"]), abs(meio - t["fim"])))
        resultado.append(mais_proximo["speaker"])
    return resultado


def suavizar(speakers: list[str], palavras: list[dict]) -> list[str]:
    """Corrige "ilhas" de uma única palavra curta atribuída a outro speaker no meio de
    uma frase contínua (erro típico nas fronteiras da diarização)."""
    s = list(speakers)
    for i in range(1, len(s) - 1):
        if s[i - 1] == s[i + 1] != s[i]:
            w, ant, prox = palavras[i], palavras[i - 1], palavras[i + 1]
            colado = (w["inicio"] - ant["fim"] < 0.3) and (prox["inicio"] - w["fim"] < 0.3)
            if colado and (w["fim"] - w["inicio"]) < 0.6 and not ant["texto"].strip().endswith(FIM_FRASE):
                s[i] = s[i - 1]
    return s


def montar_segmentos(palavras: list[dict], turnos: list[dict]) -> list[dict]:
    palavras = [w for w in palavras if w["texto"].strip()]
    if not palavras:
        return []
    speakers = suavizar(atribuir_speakers(palavras, turnos), palavras)
    segmentos: list[dict] = []
    atual: dict | None = None
    for w, spk in zip(palavras, speakers):
        if atual is not None:
            dur = w["fim"] - atual["inicio"]
            fim_frase = atual["_ultimo"].strip().endswith(FIM_FRASE)
            quebra = (spk != atual["speaker"] or w["inicio"] - atual["fim"] > PAUSA_MAX
                      or (dur > DURACAO_ALVO and fim_frase) or dur > DURACAO_MAX)
            if not quebra:
                atual["_textos"].append(w["texto"])
                atual["fim"] = w["fim"]
                atual["_ultimo"] = w["texto"]
                atual["_probs"].append(w["prob"])
                continue
            segmentos.append(atual)
        atual = {"inicio": w["inicio"], "fim": w["fim"], "speaker": spk,
                 "_textos": [w["texto"]], "_ultimo": w["texto"], "_probs": [w["prob"]]}
    segmentos.append(atual)

    saida = []
    for i, s in enumerate(segmentos, 1):
        texto = "".join(s["_textos"]).strip()
        texto = " ".join(texto.split())
        saida.append({"id": i, "inicio": round(s["inicio"], 2), "fim": round(s["fim"], 2),
                      "speaker": s["speaker"], "pessoa": None, "texto": texto,
                      "confianca": round(sum(s["_probs"]) / len(s["_probs"]), 3)})
    return saida
