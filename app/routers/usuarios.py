"""Administración de cuentas existentes en el dashboard."""

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.db import engine, usuario
from app.security import hash_contrasena, solo_administrador

router = APIRouter(prefix="/usuarios", tags=["usuarios"])
campos = (usuario.c.id_usuario, usuario.c.nombre, usuario.c.email, usuario.c.tipo_usuario)


class UsuarioDatos(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    tipo_usuario: Literal["ADMINISTRADOR", "LECTOR"]

    @field_validator("nombre", "email", mode="before")
    @classmethod
    def limpiar(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("email")
    @classmethod
    def validar_email(cls, valor: str) -> str:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", valor):
            raise ValueError("Ingresa un correo válido.")
        return valor.lower()


class UsuarioNuevo(UsuarioDatos):
    password: str = Field(min_length=8, max_length=200)


class UsuarioEdicion(UsuarioDatos):
    password: str | None = Field(default=None, min_length=8, max_length=200)


def valores(entrada):
    datos = entrada.model_dump(exclude={"password"})
    if entrada.password is not None:
        datos["contrasena_hash"] = hash_contrasena(entrada.password)
    return datos


def bloquear_cuentas(con, objetivo, administrador):
    ids = (objetivo, administrador)
    filas = con.execute(
        select(usuario.c.id_usuario, usuario.c.tipo_usuario)
        .where(usuario.c.id_usuario.in_(ids))
        .order_by(usuario.c.id_usuario)
        .with_for_update()
    ).all()
    tipos = dict(filas)
    if tipos.get(administrador) != "ADMINISTRADOR":
        raise HTTPException(403, "Esta acción requiere un usuario administrador.")
    if objetivo not in tipos:
        raise HTTPException(404, "Usuario no encontrado.")


@router.get("")
def listar(actual: dict = Depends(solo_administrador)):
    with engine.connect() as con:
        filas = con.execute(select(*campos).order_by(usuario.c.nombre, usuario.c.id_usuario)).mappings()
        return {"usuarios": [dict(fila) for fila in filas], "actual": actual["id_usuario"]}


@router.post("", status_code=201)
def crear(entrada: UsuarioNuevo, actual: dict = Depends(solo_administrador)):
    datos = valores(entrada)
    try:
        with engine.begin() as con:
            return dict(con.execute(insert(usuario).values(**datos).returning(*campos)).mappings().one())
    except IntegrityError as exc:
        if getattr(exc.orig, "pgcode", None) != "23505":
            raise
        raise HTTPException(409, "Ya existe un usuario con ese correo.") from exc


@router.put("/{id_usuario}")
def editar(id_usuario: int, entrada: UsuarioEdicion, actual: dict = Depends(solo_administrador)):
    administrador = actual["id_usuario"]
    if id_usuario == administrador and entrada.tipo_usuario != "ADMINISTRADOR":
        raise HTTPException(409, "No puedes cambiar el rol de tu propia cuenta.")
    datos = valores(entrada)
    try:
        with engine.begin() as con:
            bloquear_cuentas(con, id_usuario, administrador)
            return dict(con.execute(update(usuario).where(usuario.c.id_usuario == id_usuario)
                                    .values(**datos).returning(*campos)).mappings().one())
    except IntegrityError as exc:
        if getattr(exc.orig, "pgcode", None) != "23505":
            raise
        raise HTTPException(409, "Ya existe un usuario con ese correo.") from exc


@router.delete("/{id_usuario}", status_code=204)
def eliminar(id_usuario: int, actual: dict = Depends(solo_administrador)):
    administrador = actual["id_usuario"]
    if id_usuario == administrador:
        raise HTTPException(409, "No puedes eliminar tu propia cuenta.")
    try:
        with engine.begin() as con:
            bloquear_cuentas(con, id_usuario, administrador)
            con.execute(delete(usuario).where(usuario.c.id_usuario == id_usuario))
    except IntegrityError as exc:
        if getattr(exc.orig, "pgcode", None) != "23503":
            raise
        raise HTTPException(409, "El usuario tiene facturas registradas y debe conservarse en el historial.") from exc
    return Response(status_code=204)
