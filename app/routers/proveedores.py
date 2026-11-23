"""Catálogo de proveedores usado por el registro de facturas."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.db import engine, factura, proveedor
from app.formato import fecha_hora
from app.security import solo_administrador, usuario_actual

router = APIRouter(prefix="/proveedores", tags=["proveedores"])
campos = (proveedor.c.id_proveedor, proveedor.c.nombre)


class ProveedorEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)

    @field_validator("nombre", mode="before")
    @classmethod
    def limpiar(cls, valor):
        return " ".join(valor.split()) if isinstance(valor, str) else valor


class MontoFactura(BaseModel):
    id: int = Field(gt=0)
    monto: int = Field(gt=0, le=2_000_000_000, strict=True)
    anterior: int = Field(gt=0)


class ProveedorEdicion(ProveedorEntrada):
    facturas: list[MontoFactura] = Field(default_factory=list)

    @field_validator("facturas")
    @classmethod
    def comprobar_ids(cls, cambios):
        if len({cambio.id for cambio in cambios}) != len(cambios):
            raise ValueError("Cada factura se puede editar una vez por solicitud.")
        return cambios


@router.get("")
def listar(actual: dict = Depends(usuario_actual)):
    with engine.connect() as con:
        consulta = select(*campos).where(proveedor.c.activo).order_by(proveedor.c.nombre)
        return [dict(fila) for fila in con.execute(consulta).mappings()]


def proveedor_activo(id_proveedor):
    return (proveedor.c.id_proveedor == id_proveedor, proveedor.c.activo)


@router.get("/{id_proveedor}")
def detalle(id_proveedor: int, actual: dict = Depends(solo_administrador)):
    consulta = (
        select(*campos, factura.c.id_factura, factura.c.monto_bruto, factura.c.fecha_ingreso)
        .outerjoin(factura, factura.c.id_proveedor == proveedor.c.id_proveedor)
        .where(*proveedor_activo(id_proveedor))
        .order_by(factura.c.fecha_ingreso.desc(), factura.c.id_factura.desc())
    )
    with engine.connect() as con:
        filas = con.execute(consulta).all()
    if not filas:
        raise HTTPException(404, "Proveedor no encontrado en el catálogo.")
    return {
        "id_proveedor": id_proveedor, "nombre": filas[0].nombre,
        "facturas": [
            {"id": fila.id_factura, "monto": fila.monto_bruto, "fecha": fecha_hora(fila.fecha_ingreso)}
            for fila in filas if fila.id_factura is not None
        ],
    }


@router.post("", status_code=201)
def crear(entrada: ProveedorEntrada, actual: dict = Depends(solo_administrador)):
    consulta = (
        insert(proveedor).values(nombre=entrada.nombre, activo=True)
        .on_conflict_do_update(
            index_elements=[func.upper(func.btrim(proveedor.c.nombre))],
            set_={"activo": True}, where=proveedor.c.activo.is_(False),
        )
        .returning(*campos)
    )
    with engine.begin() as con:
        fila = con.execute(consulta).mappings().first()
        if fila is None:
            raise HTTPException(409, "Ya existe un proveedor con ese nombre.")
        return dict(fila)


@router.put("/{id_proveedor}")
def editar(id_proveedor: int, entrada: ProveedorEdicion, actual: dict = Depends(solo_administrador)):
    try:
        with engine.begin() as con:
            consulta = update(proveedor).where(*proveedor_activo(id_proveedor)).values(nombre=entrada.nombre).returning(*campos)
            guardado = con.execute(consulta).mappings().first()
            if guardado is None:
                raise HTTPException(404, "Proveedor no encontrado en el catálogo.")
            for cambio in entrada.facturas:
                resultado = con.execute(
                    update(factura).where(
                        factura.c.id_factura == cambio.id,
                        factura.c.id_proveedor == id_proveedor,
                        factura.c.monto_bruto.in_((cambio.anterior, cambio.monto)),
                    ).values(monto_bruto=cambio.monto)
                )
                if resultado.rowcount != 1:
                    raise HTTPException(409, f"La factura #{cambio.id} cambió o no pertenece al proveedor. Vuelve a abrir la edición.")
            return dict(guardado)
    except IntegrityError as exc:
        if getattr(exc.orig, "pgcode", None) != "23505":
            raise
        raise HTTPException(409, "Ese nombre ya pertenece a otro proveedor del historial.") from exc


@router.delete("/{id_proveedor}", status_code=204)
def eliminar(id_proveedor: int, actual: dict = Depends(solo_administrador)):
    with engine.begin() as con:
        resultado = con.execute(update(proveedor).where(*proveedor_activo(id_proveedor)).values(activo=False))
        if resultado.rowcount == 0:
            raise HTTPException(404, "Proveedor no encontrado en el catálogo.")
    return Response(status_code=204)
