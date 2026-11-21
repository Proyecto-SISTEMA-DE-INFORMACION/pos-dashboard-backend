"""Cliente minimo de la API REST de Gemini usando requests (sin librerias de Google)."""

import time
from dataclasses import dataclass

import requests

from app import config

URL = "{base}/v1beta/models/{modelo}:generateContent"


@dataclass
class Respuesta:
    estado: str  # OK, ERROR o LIMITE
    texto: str | None = None
    error: str | None = None
    tokens: int | None = None
    ms: int | None = None


def preguntar(instrucciones: str, historial: list[dict]) -> Respuesta:
    """historial: [{"rol": "USUARIO"|"IA", "texto": "..."}], el ultimo es la pregunta nueva."""
    if not config.AI_API_KEY:
        return Respuesta("ERROR", error="Falta AI_API_KEY en el .env del backend.")

    cuerpo = {
        "systemInstruction": {"parts": [{"text": instrucciones}]},
        "contents": [
            {"role": "user" if m["rol"] == "USUARIO" else "model", "parts": [{"text": m["texto"]}]}
            for m in historial
        ],
        "generationConfig": {"temperature": 0.3},
    }
    inicio = time.monotonic()
    try:
        r = requests.post(
            URL.format(base=config.AI_BASE_URL, modelo=config.AI_MODEL),
            headers={"x-goog-api-key": config.AI_API_KEY, "Content-Type": "application/json"},
            json=cuerpo,
            timeout=config.AI_TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as error:
        return Respuesta("ERROR", error=f"No se pudo conectar con Gemini: {error}")
    ms = int((time.monotonic() - inicio) * 1000)

    if r.status_code == 429:
        return Respuesta("LIMITE", error=f"429: {r.text[:500]}", ms=ms)
    if r.status_code != 200:
        return Respuesta("ERROR", error=f"{r.status_code}: {r.text[:500]}", ms=ms)

    try:
        datos = r.json()
        partes = datos["candidates"][0]["content"]["parts"]
        texto = "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()
    except (ValueError, KeyError, IndexError):
        return Respuesta("ERROR", error=f"Respuesta inesperada de Gemini: {r.text[:500]}", ms=ms)
    if not texto:
        motivo = datos.get("candidates", [{}])[0].get("finishReason", "sin texto")
        return Respuesta("ERROR", error=f"Gemini no devolvió texto ({motivo}).", ms=ms)

    tokens = datos.get("usageMetadata", {}).get("totalTokenCount")
    return Respuesta("OK", texto=texto, tokens=tokens, ms=ms)
