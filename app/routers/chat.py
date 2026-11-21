"""Asistente financiero: conversaciones con historial guardado en PostgreSQL."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select

from app import config, gemini
from app.analisis import resumen_financiero
from app.db import conversacion, engine, mensaje
from app.security import usuario_actual

router = APIRouter(tags=["asistente"])

MENSAJE_LIMITE = "Alcancé el límite de uso gratuito de Gemini. Intenta de nuevo en unos minutos."
MENSAJE_ERROR = "No pude responder en este momento. Intenta de nuevo más tarde."

INSTRUCCIONES = """Eres el asistente financiero de la botillería El Faro (JOSE PABST SpA), en Chile.
Respondes en español de Chile, en forma breve y clara, en texto plano (sin tablas ni markdown).
Usa SOLO los datos del resumen de abajo. Si algo no está en los datos, dilo y sugiere qué cargar
(libro de ventas en «Carga de Libro» o facturas en «Facturas»). No inventes cifras.
Montos en pesos chilenos con punto de miles, por ejemplo $1.234.567. El IVA es 19%.
IVA a pagar estimado de un mes = IVA débito de las ventas - crédito fiscal de las facturas de ese mes.
Aclara que son estimaciones y que no reemplazan la declaración ante el SII ni a un contador.

RESUMEN FINANCIERO ACTUAL:
{resumen}"""


class ChatEntrada(BaseModel):
    conversacion_id: int | None = None
    mensaje: str = Field(min_length=1, max_length=2000)


def _propia(con, id_conversacion: int, id_usuario: int):
    fila = con.execute(
        select(conversacion).where(
            conversacion.c.id_conversacion == id_conversacion,
            conversacion.c.id_usuario == id_usuario,
        )
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La conversación no existe.")
    return fila


def _texto_visible(fila) -> str:
    if fila["estado"] == "OK":
        return fila["contenido"]
    return MENSAJE_LIMITE if fila["estado"] == "LIMITE" else MENSAJE_ERROR


@router.get("/conversaciones")
def listar(actual: dict = Depends(usuario_actual)):
    with engine.connect() as con:
        filas = con.execute(
            select(conversacion.c.id_conversacion, conversacion.c.titulo)
            .where(conversacion.c.id_usuario == actual["id_usuario"])
            .order_by(conversacion.c.fecha_ultimo_mensaje.desc())
        ).all()
    return [{"id": str(f.id_conversacion), "title": f.titulo} for f in filas]


@router.get("/conversaciones/{id_conversacion}/mensajes")
def mensajes(id_conversacion: int, actual: dict = Depends(usuario_actual)):
    with engine.connect() as con:
        _propia(con, id_conversacion, actual["id_usuario"])
        filas = con.execute(
            select(mensaje).where(mensaje.c.id_conversacion == id_conversacion)
            .order_by(mensaje.c.fecha, mensaje.c.id_mensaje)
        ).mappings().all()
    return [{"r": "u" if f["rol"] == "USUARIO" else "ai", "t": _texto_visible(f)} for f in filas]


@router.delete("/conversaciones/{id_conversacion}")
def eliminar(id_conversacion: int, actual: dict = Depends(usuario_actual)):
    with engine.begin() as con:
        _propia(con, id_conversacion, actual["id_usuario"])
        con.execute(delete(conversacion).where(conversacion.c.id_conversacion == id_conversacion))
    return {"id": str(id_conversacion)}


@router.post("/chat")
def chat(entrada: ChatEntrada, actual: dict = Depends(usuario_actual)):
    pregunta = entrada.mensaje.strip()
    if not pregunta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El mensaje está vacío.")

    # 1. Guardar la pregunta (y crear la conversación si es nueva)
    with engine.begin() as con:
        if entrada.conversacion_id is None:
            fila = con.execute(
                insert(conversacion)
                .values(id_usuario=actual["id_usuario"], titulo=pregunta[:40])
                .returning(conversacion.c.id_conversacion, conversacion.c.titulo)
            ).mappings().one()
        else:
            fila = _propia(con, entrada.conversacion_id, actual["id_usuario"])
        id_conversacion, titulo = fila["id_conversacion"], fila["titulo"]

        con.execute(insert(mensaje).values(id_conversacion=id_conversacion, rol="USUARIO", contenido=pregunta))

        # Ultimos mensajes validos, en orden cronologico (incluye la pregunta recien guardada)
        recientes = con.execute(
            select(mensaje.c.rol, mensaje.c.contenido)
            .where(mensaje.c.id_conversacion == id_conversacion, mensaje.c.estado == "OK")
            .order_by(mensaje.c.fecha.desc(), mensaje.c.id_mensaje.desc())
            .limit(config.AI_MAX_HISTORIAL)
        ).all()
        resumen = resumen_financiero(con)

    historial = [{"rol": r.rol, "texto": r.contenido} for r in reversed(recientes)]
    while historial and historial[0]["rol"] != "USUARIO":  # Gemini exige empezar por el usuario
        historial.pop(0)

    # 2. Preguntar a Gemini fuera de la transaccion (puede tardar varios segundos)
    respuesta = gemini.preguntar(INSTRUCCIONES.format(resumen=resumen), historial)

    # 3. Guardar la respuesta, correcta o fallida
    with engine.begin() as con:
        con.execute(insert(mensaje).values(
            id_conversacion=id_conversacion,
            rol="IA",
            contenido=respuesta.texto,
            modelo=config.AI_MODEL,
            estado=respuesta.estado,
            mensaje_error=respuesta.error,
            datos_enviados=resumen,
            tiempo_respuesta_ms=respuesta.ms,
            tokens=respuesta.tokens,
        ))

    visible = respuesta.texto if respuesta.estado == "OK" else (
        MENSAJE_LIMITE if respuesta.estado == "LIMITE" else MENSAJE_ERROR)
    return {
        "conversacion_id": str(id_conversacion),
        "titulo": titulo,
        "respuesta": visible,
        "estado": respuesta.estado,
    }
