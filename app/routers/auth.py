from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import engine, usuario
from app.security import crear_token, hash_contrasena, usuario_actual, verificar_contrasena

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash de relleno para que un correo inexistente tarde lo mismo que uno existente
_HASH_RELLENO = hash_contrasena("relleno-no-usado")


class LoginEntrada(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


def _usuario_publico(fila) -> dict:
    return {"email": fila["email"], "nombre": fila["nombre"], "tipo": fila["tipo_usuario"]}


@router.post("/login")
def login(entrada: LoginEntrada):
    with engine.connect() as con:
        fila = con.execute(
            select(usuario).where(func.lower(usuario.c.email) == entrada.email.strip().lower())
        ).mappings().first()

    guardado = fila["contrasena_hash"] if fila else _HASH_RELLENO
    valida = verificar_contrasena(entrada.password, guardado)
    if not fila or not valida:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.")

    return {"token": crear_token(fila["id_usuario"]), "usuario": _usuario_publico(fila)}


@router.get("/me")
def yo(actual: dict = Depends(usuario_actual)):
    return _usuario_publico(actual)
