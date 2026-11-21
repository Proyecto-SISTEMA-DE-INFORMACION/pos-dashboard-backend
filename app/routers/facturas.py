from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, insert, select

from datetime import datetime

from app.db import engine, factura, proveedor
from app.routers.ventas import asegurar_temporadas
from app.formato import ZONA, fecha_hora
from app.security import solo_administrador, usuario_actual

router = APIRouter(prefix="/facturas", tags=["facturas"])


class FacturaEntrada(BaseModel):
    proveedor: str = Field(min_length=1, max_length=100)
    monto: int = Field(gt=0, le=2_000_000_000, description="Monto bruto en pesos, con IVA")

    @field_validator("proveedor")
    @classmethod
    def limpiar(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not valor:
            raise ValueError("El proveedor no puede estar vacío.")
        return valor


def _consulta():
    return (
        select(factura.c.id_factura, factura.c.monto_bruto, factura.c.fecha_ingreso, proveedor.c.nombre)
        .join(proveedor, proveedor.c.id_proveedor == factura.c.id_proveedor)
    )


def _json(f) -> dict:
    return {"id": f.id_factura, "prov": f.nombre, "monto": f.monto_bruto, "fecha": fecha_hora(f.fecha_ingreso)}


@router.get("")
def listar(actual: dict = Depends(usuario_actual)):
    with engine.connect() as con:
        filas = con.execute(_consulta().order_by(factura.c.fecha_ingreso.desc(), factura.c.id_factura.desc())).all()
    return [_json(f) for f in filas]


@router.post("", status_code=201)
def registrar(entrada: FacturaEntrada, actual: dict = Depends(solo_administrador)):
    with engine.begin() as con:
        hoy = datetime.now(ZONA).date()
        asegurar_temporadas(con, {hoy})
        id_proveedor = con.execute(
            select(proveedor.c.id_proveedor)
            .where(func.upper(func.btrim(proveedor.c.nombre)) == entrada.proveedor.upper())
        ).scalar()
        if id_proveedor is None:
            id_proveedor = con.execute(
                insert(proveedor).values(nombre=entrada.proveedor).returning(proveedor.c.id_proveedor)
            ).scalar_one()
        id_factura = con.execute(
            insert(factura)
            .values(id_proveedor=id_proveedor, monto_bruto=entrada.monto, fecha_factura=hoy, id_usuario=actual["id_usuario"],
                    id_temporada=None)  # lo asigna el trigger segun fecha_factura
            .returning(factura.c.id_factura)
        ).scalar_one()
        fila = con.execute(_consulta().where(factura.c.id_factura == id_factura)).one()
    return _json(fila)
