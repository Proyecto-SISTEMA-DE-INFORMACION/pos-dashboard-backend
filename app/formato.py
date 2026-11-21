"""Formatos de fecha y dinero iguales a los que muestra el frontend (es-CL)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app import config

ZONA = ZoneInfo(config.ZONA_HORARIA)
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def fecha_hora(valor: datetime | None) -> str:
    """Igual que toLocaleString('es-CL'): 21-11-2026, 19:30:00"""
    if valor is None:
        return ""
    return valor.astimezone(ZONA).strftime("%d-%m-%Y, %H:%M:%S")


def clp(valor: float | int | None) -> str:
    """$1.234.567"""
    return "$" + f"{round(valor or 0):,}".replace(",", ".")
