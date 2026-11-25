"""Metas de ingresos por mes. Todos las ven; solo un administrador las cambia."""

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.db import engine, meta_mensual, usuario
from app.formato import fecha_hora
from app.security import solo_administrador, usuario_actual

router = APIRouter(prefix="/metas", tags=["metas"])

PATRON_MES = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class MetaEntrada(BaseModel):
    monto: int = Field(gt=0, le=100_000_000_000, strict=True, description="Meta en pesos, con IVA")


def _mes(texto: str) -> date:
    """'2026-03' -> date(2026, 3, 1)"""
    coincidencia = PATRON_MES.match(texto)
    if not coincidencia or not 2000 <= int(coincidencia.group(1)) <= 2100:
        raise HTTPException(422, "El mes debe tener el formato AAAA-MM, por ejemplo 2026-03.")
    return date(int(coincidencia.group(1)), int(coincidencia.group(2)), 1)


def _consulta():
    return (
        select(meta_mensual.c.mes, meta_mensual.c.monto, meta_mensual.c.fecha_actualizacion,
               usuario.c.nombre)
        .select_from(meta_mensual.outerjoin(usuario, usuario.c.id_usuario == meta_mensual.c.id_usuario))
    )


def _json(fila) -> dict:
    return {
        "mes": fila.mes.strftime("%Y-%m"),
        "monto": fila.monto,
        "usuario": fila.nombre,
        "actualizado": fecha_hora(fila.fecha_actualizacion),
    }


@router.get("")
def listar(actual: dict = Depends(usuario_actual)):
    with engine.connect() as con:
        filas = con.execute(_consulta().order_by(meta_mensual.c.mes.desc())).all()
    return [_json(f) for f in filas]


@router.put("/{mes}")
def guardar(mes: str, entrada: MetaEntrada, actual: dict = Depends(solo_administrador)):
    primer_dia = _mes(mes)
    with engine.begin() as con:
        sentencia = insert(meta_mensual).values(
            mes=primer_dia, monto=entrada.monto, id_usuario=actual["id_usuario"],
        )
        con.execute(sentencia.on_conflict_do_update(
            index_elements=[meta_mensual.c.mes],
            set_={"monto": entrada.monto, "id_usuario": actual["id_usuario"],
                  "fecha_actualizacion": func.now()},
        ))
        fila = con.execute(_consulta().where(meta_mensual.c.mes == primer_dia)).one()
    return _json(fila)


@router.delete("/{mes}", status_code=204)
def eliminar(mes: str, actual: dict = Depends(solo_administrador)):
    primer_dia = _mes(mes)
    with engine.begin() as con:
        borradas = con.execute(delete(meta_mensual).where(meta_mensual.c.mes == primer_dia)).rowcount
    if not borradas:
        raise HTTPException(404, "Ese mes no tiene meta registrada.")
    return Response(status_code=204)
