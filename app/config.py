"""Configuracion leida desde el archivo .env de la raiz del proyecto."""

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _entero("DB_PORT", 5432)
DB_NAME = os.getenv("DB_NAME", "botilleria")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_SCHEMA = os.getenv("DB_SCHEMA", "botilleria")

SECRET_KEY = os.getenv("SECRET_KEY", "")
TOKEN_HORAS = _entero("TOKEN_HORAS", 12)

# Origenes que pueden llamar a la API (el frontend de Next.js)
FRONTEND_ORIGINS = [
    o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]

AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gemini-3.8-flash")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
AI_MAX_HISTORIAL = _entero("AI_MAX_HISTORIAL", 20)
AI_TIMEOUT_SEGUNDOS = _entero("AI_TIMEOUT_SEGUNDOS", 60)

ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/Santiago")
MAX_MB_ARCHIVO = _entero("MAX_MB_ARCHIVO", 20)

if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY falta o es muy corta en el .env (minimo 32 caracteres). "
        "Genera una con: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
