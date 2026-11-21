"""Carga del libro de ventas, historial de cargas y documentos de venta."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app import config
from app.db import archivo, engine, medio_pago, temporada, venta
from app.etl import ErrorLibro, leer_libro, resolver_medio
from app.formato import fecha_hora
from app.security import solo_administrador, usuario_actual

router = APIRouter(tags=["ventas"])

TIPO_POR_SERIE = {"EFECTIVO": "Boleta efectivo", "TARJETA": "Boleta tarjeta"}


def _carga_json(fila) -> dict:
    nuevos, omitidos = fila["registros_nuevos"], fila["registros_omitidos"]
    return {
        "id": str(fila["id_carga"]),
        "name": fila["nombre_archivo"],
        "fecha": fecha_hora(fila["fecha_carga"]),
        "nuevos": nuevos,
        "omitidos": omitidos,
        "procesados": nuevos + omitidos,
    }


def asegurar_temporadas(con, fechas: set[date]) -> None:
    """Crea temporadas de julio a junio para las fechas que no tengan una."""
    existentes = con.execute(select(temporada.c.fecha_inicio, temporada.c.fecha_fin)).all()
    faltan = {f for f in fechas if not any(i <= f <= fin for i, fin in existentes)}
    anios = sorted({f.year if f.month >= 7 else f.year - 1 for f in faltan})
    for anio in anios:
        con.execute(insert(temporada).values(
            nombre=f"{anio}-{anio + 1}",
            fecha_inicio=date(anio, 7, 1),
            fecha_fin=date(anio + 1, 6, 30),
        ))


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def subir_libro(
    request: Request,
    nombre: str = Query(..., min_length=1, max_length=255, description="Nombre del archivo .xlsx"),
    actual: dict = Depends(solo_administrador),
):
    """Recibe el .xlsx como cuerpo binario (application/octet-stream)."""
    if not nombre.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo debe ser formato .xlsx")

    contenido = await request.body()
    if not contenido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo llegó vacío.")
    if len(contenido) > config.MAX_MB_ARCHIVO * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"El archivo supera el máximo de {config.MAX_MB_ARCHIVO} MB.")

    try:
        libro = leer_libro(contenido)
    except ErrorLibro as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))

    with engine.begin() as con:
        catalogo = {
            f["nombre_medio"].upper(): dict(f)
            for f in con.execute(select(medio_pago)).mappings()
        }
        if not catalogo:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "No hay medios de pago en la base. Ejecuta: python db/crear_db.py --reset --con-catalogos",
            )

        desconocidos = sorted({f.medio for f in libro.filas if resolver_medio(f.medio, catalogo) is None})
        if desconocidos:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Medios de pago desconocidos: " + ", ".join(desconocidos)
                + ". Agrégalos a la tabla medio_pago antes de cargar.",
            )

        asegurar_temporadas(con, {f.fecha for f in libro.filas})

        id_carga = con.execute(
            insert(archivo).values(nombre_archivo=nombre).returning(archivo.c.id_carga)
        ).scalar_one()

        filas = []
        for f in libro.filas:
            medio = resolver_medio(f.medio, catalogo)
            filas.append({
                "serie": medio["serie"],
                "numero_boleta": f.numero_boleta,
                "fecha": f.fecha,
                "valor_neto": f.valor_neto,
                "valor_iva": f.valor_iva,
                "valor_total": f.valor_total,
                "id_medio": medio["id_medio"],
                "id_carga": id_carga,
                "id_temporada": None,  # lo asigna el trigger segun la fecha
            })

        try:
            insertadas = con.execute(
                pg_insert(venta)
                .on_conflict_do_nothing(index_elements=["serie", "numero_boleta"])
                .returning(venta.c.id_venta),
                filas,
            ).all()
        except IntegrityError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"La base rechazó los datos: {error.orig}".strip())

        nuevos = len(insertadas)
        con.execute(
            update(archivo)
            .where(archivo.c.id_carga == id_carga)
            .values(registros_nuevos=nuevos, registros_omitidos=len(filas) - nuevos)
        )
        fila = con.execute(select(archivo).where(archivo.c.id_carga == id_carga)).mappings().one()

    return {**_carga_json(fila), "advertencias": libro.advertencias}


@router.get("/cargas")
def listar_cargas(actual: dict = Depends(usuario_actual)):
    with engine.connect() as con:
        filas = con.execute(select(archivo).order_by(archivo.c.id_carga.desc())).mappings().all()
    return [_carga_json(f) for f in filas]


@router.delete("/cargas/{id_carga}")
def eliminar_carga(id_carga: int, actual: dict = Depends(solo_administrador)):
    with engine.begin() as con:
        existe = con.execute(select(archivo.c.id_carga).where(archivo.c.id_carga == id_carga)).first()
        if not existe:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "La carga no existe.")
        borradas = con.execute(delete(venta).where(venta.c.id_carga == id_carga)).rowcount
        con.execute(delete(archivo).where(archivo.c.id_carga == id_carga))
    return {"id": str(id_carga), "ventas_eliminadas": borradas}


@router.get("/documentos")
def listar_documentos(actual: dict = Depends(usuario_actual)):
    """Todas las ventas con los campos que usa el frontend."""
    consulta = (
        select(
            venta.c.numero_boleta, venta.c.fecha, venta.c.serie,
            venta.c.valor_neto, venta.c.valor_iva, venta.c.valor_total, venta.c.id_carga,
            medio_pago.c.nombre_medio, medio_pago.c.cuenta_como_ingreso,
        )
        .join(medio_pago, medio_pago.c.id_medio == venta.c.id_medio)
        .order_by(venta.c.fecha, venta.c.serie, venta.c.numero_boleta)
    )
    with engine.connect() as con:
        filas = con.execute(consulta).all()
    return [
        {
            "folio": str(int(f.numero_boleta)),
            "fecha": f.fecha.isoformat(),
            "tipo": TIPO_POR_SERIE.get(f.serie, f.serie),
            "neto": f.valor_neto,
            "iva": f.valor_iva,
            "total": f.valor_total,
            # El frontend suma solo los "Vigente"; los medios que no son ingreso quedan aparte
            "estado": "Vigente" if f.cuenta_como_ingreso else "Pendiente",
            "medio": f.nombre_medio,
            "src": str(f.id_carga),
        }
        for f in filas
    ]
