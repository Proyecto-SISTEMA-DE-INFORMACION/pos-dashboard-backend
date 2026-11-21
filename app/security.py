"""Contrasenas cifradas y tokens de sesion usando solo la libreria estandar de Python."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app import config
from app.db import engine, usuario

ITERACIONES = 600_000
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------- contrasenas
def hash_contrasena(contrasena: str) -> str:
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal.encode(), ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal}${digest.hex()}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        algoritmo, iteraciones, sal, esperado = guardado.split("$")
    except ValueError:
        return False
    if algoritmo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal.encode(), int(iteraciones))
    return hmac.compare_digest(digest.hex(), esperado)


# ---------------------------------------------------------------- tokens
def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _desde_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _firma(cuerpo: str) -> str:
    return _b64(hmac.new(config.SECRET_KEY.encode(), cuerpo.encode(), hashlib.sha256).digest())


def crear_token(id_usuario: int) -> str:
    datos = {"sub": id_usuario, "exp": int(time.time()) + config.TOKEN_HORAS * 3600}
    cuerpo = _b64(json.dumps(datos, separators=(",", ":")).encode())
    return f"{cuerpo}.{_firma(cuerpo)}"


def leer_token(token: str) -> int | None:
    try:
        cuerpo, firma = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(firma, _firma(cuerpo)):
        return None
    try:
        datos = json.loads(_desde_b64(cuerpo))
    except (ValueError, json.JSONDecodeError):
        return None
    if datos.get("exp", 0) < time.time():
        return None
    return datos.get("sub")


# ---------------------------------------------------------------- dependencias
def usuario_actual(credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    no_autorizado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesion expirada o no valida. Inicia sesion nuevamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credenciales is None:
        raise no_autorizado
    id_usuario = leer_token(credenciales.credentials)
    if id_usuario is None:
        raise no_autorizado
    with engine.connect() as con:
        fila = con.execute(
            select(usuario.c.id_usuario, usuario.c.email, usuario.c.nombre, usuario.c.tipo_usuario)
            .where(usuario.c.id_usuario == id_usuario)
        ).mappings().first()
    if fila is None:
        raise no_autorizado
    return dict(fila)


def solo_administrador(actual: dict = Depends(usuario_actual)) -> dict:
    if actual["tipo_usuario"] != "ADMINISTRADOR":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta accion requiere un usuario administrador.")
    return actual
