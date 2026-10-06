"""Conversão entre segundos e textos HH:MM:SS."""
from __future__ import annotations


def formatar(segundos: float | None, decimos: bool = False) -> str:
    if segundos is None:
        return ""
    segundos = max(0.0, float(segundos))
    if decimos:
        total_d = int(round(segundos * 10))
        h, resto = divmod(total_d, 36000)
        m, resto = divmod(resto, 600)
        s, d = divmod(resto, 10)
        return f"{h:02d}:{m:02d}:{s:02d}.{d}"
    total = int(segundos)
    h, resto = divmod(total, 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def formatar_srt(segundos: float) -> str:
    ms = int(round(max(0.0, segundos) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def interpretar(texto: str | float | int) -> float:
    """Aceita '1:02:03.5', '02:03', '123.4' ou número."""
    if isinstance(texto, (int, float)):
        return float(texto)
    t = str(texto).strip().replace(",", ".")
    if not t:
        raise ValueError("tempo vazio")
    partes = t.split(":")
    if len(partes) > 3:
        raise ValueError(f"tempo inválido: {texto}")
    total = 0.0
    for p in partes:
        total = total * 60 + float(p)
    return total
