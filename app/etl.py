"""Lectura del libro de ventas real (hoja LIBROV) con pandas.

Formato esperado: unas filas de titulo, luego un encabezado con
FECHA | NRO.BOL | NETO | IVA | TOTAL | FORMA 1 | MONTO 1 | FORMA 2 | MONTO 2 | FORMA 3 | MONTO 3
y al final una fila de totales (sin fecha), que se descarta.
"""

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

COLUMNAS_OBLIGATORIAS = ["FECHA", "NRO.BOL", "TOTAL", "FORMA 1"]
MAX_FILAS_ENCABEZADO = 20


class ErrorLibro(ValueError):
    """Error con un mensaje listo para mostrar al usuario."""


@dataclass
class FilaVenta:
    numero_boleta: str
    fecha: date
    valor_neto: int
    valor_iva: int
    valor_total: int
    medio: str  # texto tal como viene en FORMA 1 (normalizado a mayusculas)


@dataclass
class LibroLeido:
    filas: list[FilaVenta]
    advertencias: list[str] = field(default_factory=list)


def _norm(texto) -> str:
    texto = unicodedata.normalize("NFD", str(texto if texto is not None else ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip().upper()


def _fecha(valor) -> date | None:
    texto = str(valor).strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", texto)
    if m:
        dia, mes, anio = map(int, m.groups())
    else:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", texto)  # celda con formato fecha de Excel
        if not m:
            return None
        anio, mes, dia = map(int, m.groups())
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def _redondear(serie: pd.Series) -> pd.Series:
    # Redondeo comercial (0,5 hacia arriba), no el redondeo bancario de pandas
    return np.sign(serie) * np.floor(np.abs(serie) + 0.5)


def leer_libro(contenido: bytes) -> LibroLeido:
    try:
        crudo = pd.read_excel(io.BytesIO(contenido), header=None, dtype=str, engine="openpyxl")
    except Exception as error:  # archivo corrupto o que no es Excel
        raise ErrorLibro("No se pudo leer el archivo. Verifica que sea un Excel .xlsx valido.") from error

    fila_encabezado = None
    for i in range(min(MAX_FILAS_ENCABEZADO, len(crudo))):
        if "NRO.BOL" in {_norm(c) for c in crudo.iloc[i].tolist()}:
            fila_encabezado = i
            break
    if fila_encabezado is None:
        raise ErrorLibro(
            "No se encontro la columna NRO.BOL. El archivo debe ser el libro de ventas (hoja LIBROV)."
        )

    encabezados = [_norm(c) for c in crudo.iloc[fila_encabezado].tolist()]
    faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in encabezados]
    if faltantes:
        raise ErrorLibro("Faltan columnas en el libro de ventas: " + ", ".join(faltantes))

    datos = crudo.iloc[fila_encabezado + 1:].copy()
    datos.columns = encabezados
    col = lambda nombre: datos[nombre] if nombre in datos.columns else pd.Series(None, index=datos.index)

    fechas = col("FECHA").map(_fecha)
    con_fecha = fechas.notna()
    if not con_fecha.any():
        raise ErrorLibro("No se encontraron ventas con fecha valida (formato dd/mm/aaaa).")

    datos = datos[con_fecha]
    fechas = fechas[con_fecha]
    boletas = col("NRO.BOL").fillna("").str.strip()
    total = pd.to_numeric(col("TOTAL"), errors="coerce")
    neto = pd.to_numeric(col("NETO"), errors="coerce")
    medio = col("FORMA 1").fillna("").map(_norm)

    problemas = []
    malas_boletas = ~boletas.str.fullmatch(r"\d{1,10}")
    if malas_boletas.any():
        problemas.append(f"{int(malas_boletas.sum())} filas con NRO.BOL vacio o no numerico")
    if total.isna().any():
        problemas.append(f"{int(total.isna().sum())} filas con TOTAL vacio o no numerico")
    if (total < 0).any():
        problemas.append(f"{int((total < 0).sum())} filas con TOTAL negativo")
    if (medio == "").any():
        problemas.append(f"{int((medio == '').sum())} filas sin FORMA 1 (medio de pago)")
    if problemas:
        primera = datos.index[(malas_boletas | total.isna() | (total < 0) | (medio == "")).to_numpy()][0]
        raise ErrorLibro(
            "El archivo tiene datos invalidos: " + "; ".join(problemas)
            + f". Primera fila con problema: {primera + 1} del Excel."
        )

    total_r = _redondear(total).astype("int64")
    neto_r = _redondear(neto.fillna(total / 1.19)).astype("int64")
    neto_r = neto_r.clip(lower=0, upper=total_r)
    iva_r = total_r - neto_r

    advertencias = []
    for n in (2, 3):
        monto = pd.to_numeric(col(f"MONTO {n}"), errors="coerce").fillna(0)
        if (monto > 0).any():
            advertencias.append(
                f"{int((monto > 0).sum())} boletas traen FORMA {n}: se registran con el medio de FORMA 1."
            )

    filas = [
        FilaVenta(b, f, int(ne), int(iv), int(t), m)
        for b, f, ne, iv, t, m in zip(boletas, fechas, neto_r, iva_r, total_r, medio)
    ]
    return LibroLeido(filas=filas, advertencias=advertencias)


def resolver_medio(texto: str, catalogo: dict[str, dict]) -> dict | None:
    """Busca el medio en el catalogo. Acepta nombres cortados por el sistema
    de caja, como "PENDIENTE DE PA" para "PENDIENTE DE PAGO"."""
    if texto in catalogo:
        return catalogo[texto]
    candidatos = [v for k, v in catalogo.items() if k.startswith(texto)]
    return candidatos[0] if len(candidatos) == 1 else None
