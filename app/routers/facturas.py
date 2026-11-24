from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from datetime import datetime

from app.db import engine, factura, medio_pago, proveedor, venta
from app.exportacion_facturas import generar_excel
from app.routers.ventas import asegurar_temporadas
from app.formato import ZONA, fecha_hora
from app.security import solo_administrador, usuario_actual

router = APIRouter(prefix="/facturas", tags=["facturas"])


class FacturaEntrada(BaseModel):
    id_proveedor: int = Field(gt=0, le=2_147_483_647, strict=True)
    monto: int = Field(gt=0, le=2_000_000_000, description="Monto bruto en pesos, con IVA")


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


@router.get("/exportacion")
def exportar(actual: dict = Depends(usuario_actual)):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as con:
        filas = con.execute(_consulta().order_by(factura.c.fecha_ingreso.desc(), factura.c.id_factura.desc())).all()
        debito = con.scalar(
            select(func.coalesce(func.sum(venta.c.valor_iva), 0))
            .select_from(venta.join(medio_pago, medio_pago.c.id_medio == venta.c.id_medio))
            .where(medio_pago.c.cuenta_como_ingreso)
        )
    return Response(
        generar_excel([_json(f) for f in filas], debito),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="compras-proveedores-iva.xlsx"'},
    )


@router.post("", status_code=201)
def registrar(entrada: FacturaEntrada, actual: dict = Depends(solo_administrador)):
    with engine.begin() as con:
        hoy = datetime.now(ZONA).date()
        id_proveedor = con.execute(
            select(proveedor.c.id_proveedor)
            .where(proveedor.c.id_proveedor == entrada.id_proveedor, proveedor.c.activo)
            .with_for_update(read=True)
        ).scalar_one_or_none()
        if id_proveedor is None:
            raise HTTPException(409, "El proveedor seleccionado no está activo en el catálogo.")
        asegurar_temporadas(con, {hoy})
        id_factura = con.execute(
            insert(factura)
            .values(id_proveedor=id_proveedor, monto_bruto=entrada.monto, fecha_factura=hoy, id_usuario=actual["id_usuario"],
                    id_temporada=None)  # lo asigna el trigger segun fecha_factura
            .returning(factura.c.id_factura)
        ).scalar_one()
        fila = con.execute(_consulta().where(factura.c.id_factura == id_factura)).one()
    return _json(fila)

@router.delete("/{id_factura}", status_code=204)
def eliminar(id_factura: int, actual: dict = Depends(solo_administrador)):
    try:
        with engine.begin() as con:
            borradas = con.execute(
                delete(factura).where(factura.c.id_factura == id_factura)
            ).rowcount
            if not borradas:
                raise HTTPException(404, "La factura no existe.")
    except IntegrityError:
        raise HTTPException(409, "No se puede eliminar la factura porque tiene registros asociados.")
    return Response(status_code=204)